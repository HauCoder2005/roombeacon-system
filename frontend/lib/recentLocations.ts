export interface StoredLocation {
  districtId?: string;
  districtName?: string;
  wardId?: string;
  wardName?: string;
  label: string;
}

const STORAGE_KEY = "roombeacon_recent_locations";

export function getRecentLocations(): StoredLocation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.slice(0, 5);
    }
  } catch {
    // localStorage disabled or corrupted
  }
  return [];
}

export function saveRecentLocation(loc: StoredLocation): void {
  if (typeof window === "undefined") return;
  try {
    const current = getRecentLocations();
    const filtered = current.filter(
      (item) => !(item.districtId === loc.districtId && item.wardId === loc.wardId)
    );
    const updated = [loc, ...filtered].slice(0, 5);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // ignore
  }
}

export function clearRecentLocations(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
