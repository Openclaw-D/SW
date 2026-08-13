import { useEffect, useRef } from "react";
import type { RefObject } from "react";

export function useLockedWheel<T extends HTMLElement>(
  elementRef: RefObject<T | null>,
  onWheel: (event: WheelEvent) => void,
) {
  const onWheelRef = useRef(onWheel);
  onWheelRef.current = onWheel;

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const lockWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      onWheelRef.current(event);
    };
    element.addEventListener("wheel", lockWheel, { passive: false });
    return () => element.removeEventListener("wheel", lockWheel);
  });
}
