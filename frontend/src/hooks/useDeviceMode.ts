import { useEffect, useState } from "react";

export type DeviceMode = "mobile" | "desktop";

function detectDeviceMode(): DeviceMode {
  if (typeof window === "undefined") return "desktop";
  const coarsePointer = window.matchMedia("(hover: none) and (pointer: coarse)").matches;
  const narrowViewport = window.matchMedia("(max-width: 820px)").matches;
  return coarsePointer || narrowViewport ? "mobile" : "desktop";
}

export function useDeviceMode(): DeviceMode {
  const [deviceMode, setDeviceMode] = useState<DeviceMode>(() => detectDeviceMode());

  useEffect(() => {
    const update = () => setDeviceMode(detectDeviceMode());
    const pointerQuery = window.matchMedia("(hover: none) and (pointer: coarse)");
    const viewportQuery = window.matchMedia("(max-width: 820px)");
    update();
    pointerQuery.addEventListener("change", update);
    viewportQuery.addEventListener("change", update);
    window.addEventListener("resize", update);
    return () => {
      pointerQuery.removeEventListener("change", update);
      viewportQuery.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.device = deviceMode;
  }, [deviceMode]);

  return deviceMode;
}
