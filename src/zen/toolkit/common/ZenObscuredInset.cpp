/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#include "mozilla/ZenObscuredInset.h"

#include "nsPresContext.h"
#include "nsIDocShell.h"
#include "nsIFrame.h"
#include "nsIReflowCallback.h"
#include "nsLayoutUtils.h"
#include "nsStyleStruct.h"
#include "nsThreadUtils.h"

#include "mozilla/PresShell.h"
#include "mozilla/ScrollContainerFrame.h"
#include "mozilla/TimeStamp.h"
#include "mozilla/dom/BrowsingContext.h"
#include "mozilla/dom/Document.h"

namespace mozilla::zen {

nscoord ObscuredTopInset(const nsPresContext* aPresContext) {
  if (!aPresContext || aPresContext->IsPaginated() ||
      !aPresContext->IsRootContentDocumentCrossProcess()) {
    return 0;
  }
  dom::BrowsingContext* bc = aPresContext->Document()->GetBrowsingContext();
  if (!bc || !bc->IsTop()) {
    return 0;
  }
  const int32_t devPixels = bc->GetZenObscuredTopInset();
  if (devPixels <= 0) {
    return 0;
  }
  // Device pixels keep the band a constant physical height under full zoom.
  return aPresContext->DevPixelsToAppUnits(devPixels);
}

void ObscuredTopInsetChanged(dom::BrowsingContext* aContext) {
  nsIDocShell* docShell = aContext->GetDocShell();
  if (!docShell) {
    return;  // Laid out in another process; its own DidSet handles it.
  }
  RefPtr<PresShell> presShell = docShell->GetPresShell();
  if (!presShell) {
    return;  // The first layout of the next document reads the field.
  }
  if (nsIFrame* rootFrame = presShell->GetRootFrame()) {
    // Dirtying the viewport subtree also reflows fixed-position children,
    // whose containing block origin moves even when its size does not.
    presShell->FrameNeedsReflow(rootFrame, IntrinsicDirty::None,
                                NS_FRAME_IS_DIRTY);
  }
}

NS_DECLARE_FRAME_PROPERTY_SMALL_VALUE(ZenBandColorProperty, nscolor)
NS_DECLARE_FRAME_PROPERTY_SMALL_VALUE(ZenBandPendingProperty, bool)
NS_DECLARE_FRAME_PROPERTY_SMALL_VALUE(ZenBandSampleQueuedProperty, bool)

// Talos samples with elementsFromPoint and stops at a layer with alpha
// >= 0.99; 253/255 is the nearest 8-bit equivalent.
static bool IsOpaqueLayer(nscolor aColor) { return NS_GET_A(aColor) >= 253; }

// Top color of a single top-to-bottom, non-repeating linear-gradient layer.
static Maybe<nscolor> GradientTopColor(const nsIFrame* aFrame) {
  const nsStyleImageLayers& layers = aFrame->StyleBackground()->mImage;
  if (layers.mImageCount != 1 || !layers.mLayers[0].mImage.IsGradient()) {
    return Nothing();
  }
  const StyleGradient& gradient = *layers.mLayers[0].mImage.AsGradient();
  if (!gradient.IsLinear() || gradient.Repeating()) {
    return Nothing();
  }
  const auto& linear = gradient.AsLinear();
  const bool modern = linear.compat_mode == StyleGradientCompatMode::Modern;
  const StyleLineDirection& direction = linear.direction;
  const bool toBottom =
      direction.IsVertical()
          ? modern !=
                (direction.AsVertical() == StyleVerticalPositionKeyword::Top)
          : direction.IsAngle() && modern &&
                std::abs(direction.AsAngle().ToDegrees() - 180.0f) < 0.5f;
  if (!toBottom) {
    return Nothing();
  }
  for (const auto& item : linear.items.AsSpan()) {
    if (item.IsInterpolationHint()) {
      continue;
    }
    const StyleColor& color = item.IsSimpleColorStop()
                                  ? item.AsSimpleColorStop()
                                  : item.AsComplexColorStop().color;
    return Some(
        color.ResolveColor(aFrame->StyleText()->mColor).ToColor(aFrame));
  }
  return Nothing();
}

// Composited background of the in-flow paint stack at aPoint (viewport
// coordinates) over the canvas color, as Talos's band color script does.
static nscolor TopEdgeColor(nsIFrame* aViewport, const nsPoint& aPoint,
                            nscolor aCanvas) {
  AutoTArray<nsIFrame*, 32> frames;
  nsLayoutUtils::GetFramesForArea(
      RelativeTo{aViewport}, nsRect(aPoint, nsSize(1, 1)), frames,
      {{nsLayoutUtils::FrameForPointOption::IgnorePaintSuppression,
        nsLayoutUtils::FrameForPointOption::IgnoreCrossDoc}});
  AutoTArray<nsIContent*, 32> seen;
  AutoTArray<nscolor, 8> layers;  // Topmost first.
  for (nsIFrame* f : frames) {
    nsIContent* content = f->GetContent();
    if (content && !content->IsElement()) {
      content = content->GetFlattenedTreeParentElement();
    }
    if (!content || content->IsInNativeAnonymousSubtree() ||
        seen.Contains(content) || seen.Length() >= 40) {
      continue;
    }
    seen.AppendElement(content);
    const nsIFrame* styled = content->GetPrimaryFrame();
    // The band continues the document's own top edge. Fixed headers sit
    // below the band and never scroll into it, so they don't color it.
    if (!styled || nsLayoutUtils::IsInPositionFixedSubtree(styled)) {
      continue;
    }
    // Images paint above the background color.
    if (Maybe<nscolor> top = GradientTopColor(styled); top && NS_GET_A(*top)) {
      layers.AppendElement(*top);
      if (IsOpaqueLayer(*top)) {
        break;
      }
    }
    const nscolor color = styled->StyleBackground()->BackgroundColor(styled);
    if (NS_GET_A(color)) {
      layers.AppendElement(color);
      if (IsOpaqueLayer(color)) {
        break;
      }
    }
  }
  nscolor out = aCanvas;
  for (size_t i = layers.Length(); i-- > 0;) {
    out = NS_ComposeColors(out, layers[i]);
  }
  return NS_RGB(NS_GET_R(out), NS_GET_G(out), NS_GET_B(out));
}

static void UpdateBandColor(nsIFrame* aCanvas) {
  nsPresContext* pc = aCanvas->PresContext();
  PresShell* presShell = pc->PresShell();
  const nscoord inset = ObscuredTopInset(pc);
  ScrollContainerFrame* sf = presShell->GetRootScrollContainerFrame();
  nsIFrame* viewport = presShell->GetRootFrame();
  if (!inset || !sf || !viewport) {
    if (aCanvas->HasProperty(ZenBandColorProperty())) {
      aCanvas->RemoveProperty(ZenBandColorProperty());
      aCanvas->InvalidateFrame();
    }
    return;
  }
  // The band shows only at the top; a stack sampled while scrolled (or
  // pulled past the top) describes other content, so keep the last color.
  const nscoord scrollY = sf->GetScrollPosition().y;
  if (scrollY > nsPresContext::CSSPixelsToAppUnits(2) || scrollY < 0) {
    return;
  }
  // The canvas as Gecko paints it: html/body background, else the default
  // (light or dark) document background.
  const nscolor canvas = NS_ComposeColors(
      NS_RGB(255, 255, 255), presShell->GetCanvasBackground(false).mColor);
  // A few px below the band, so thin top borders don't decide.
  const nsRect port = sf->GetScrollPortRect();
  const nscoord y = port.y + inset + nsPresContext::CSSPixelsToAppUnits(6);
  auto at = [&](double aFraction) {
    const nscoord x = port.x + NSToCoordRound(port.width * aFraction);
    return TopEdgeColor(viewport,
                        nsPoint(std::min(x, port.XMost() - 1), y), canvas);
  };
  const nscolor c[3] = {at(0.15), at(0.5), at(0.85)};
  const nscolor pick = (c[0] == c[1] || c[0] == c[2]) ? c[0] : c[1];

  bool found = false;
  const nscolor old = aCanvas->GetProperty(ZenBandColorProperty(), &found);
  if (!found || old != pick) {
    aCanvas->SetProperty(ZenBandColorProperty(), pick);
    aCanvas->InvalidateFrame();
  }
}

class BandColorCallback final : public nsIReflowCallback {
 public:
  explicit BandColorCallback(nsIFrame* aCanvas) : mCanvas(aCanvas) {}

  bool ReflowFinished() override {
    if (nsIFrame* canvas = mCanvas.GetFrame()) {
      canvas->RemoveProperty(ZenBandPendingProperty());
      UpdateBandColor(canvas);
    }
    delete this;
    return false;
  }

  void ReflowCallbackCanceled() override {
    if (nsIFrame* canvas = mCanvas.GetFrame()) {
      canvas->RemoveProperty(ZenBandPendingProperty());
    }
    delete this;
  }

 private:
  WeakFrame mCanvas;
};

void ScheduleBandColorUpdate(nsIFrame* aCanvasFrame) {
  if (aCanvasFrame->GetProperty(ZenBandPendingProperty())) {
    return;
  }
  aCanvasFrame->SetProperty(ZenBandPendingProperty(), true);
  aCanvasFrame->PresShell()->PostReflowCallback(
      new BandColorCallback(aCanvasFrame));
}

void NoteBandPainted(nsIFrame* aCanvasFrame) {
  // Something on the page repainted (an image loaded, a style or class
  // changed, a transition ran): Talos re-reads the top edge for these with a
  // 250 ms throttle. Painting can't hit-test, so sample afterwards.
  static constexpr uint32_t kThrottleMs = 250;
  if (aCanvasFrame->GetProperty(ZenBandSampleQueuedProperty())) {
    return;
  }
  aCanvasFrame->SetProperty(ZenBandSampleQueuedProperty(), true);
  // The canvas frame can be replaced meanwhile; sample whichever is current.
  RefPtr<PresShell> presShell = aCanvasFrame->PresShell();
  NS_DelayedDispatchToCurrentThread(
      NS_NewRunnableFunction("zen::NoteBandPainted",
                             [presShell]() {
                               if (presShell->IsDestroying()) {
                                 return;
                               }
                               ScrollContainerFrame* root =
                                   presShell->GetRootScrollContainerFrame();
                               nsIFrame* canvas =
                                   root ? root->GetScrolledFrame() : nullptr;
                               if (!canvas || !canvas->IsCanvasFrame()) {
                                 return;
                               }
                               canvas->RemoveProperty(
                                   ZenBandSampleQueuedProperty());
                               UpdateBandColor(canvas);
                             }),
      kThrottleMs);
}

Maybe<nscolor> BandColor(const nsIFrame* aCanvasFrame) {
  bool found = false;
  const nscolor color =
      aCanvasFrame->GetProperty(ZenBandColorProperty(), &found);
  return found ? Some(color) : Nothing();
}

}  // namespace mozilla::zen

using BrowsingContext = mozilla::dom::BrowsingContext;

void BrowsingContext::DidSet(FieldIndex<IDX_ZenObscuredTopInset>,
                             int32_t aOldValue) {
  MOZ_ASSERT(IsTop());
  if (GetZenObscuredTopInset() == aOldValue) {
    return;
  }
  mozilla::zen::ObscuredTopInsetChanged(this);
}
