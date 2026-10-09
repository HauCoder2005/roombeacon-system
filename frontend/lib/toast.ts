export type ToastType = "info" | "warning" | "error" | "success";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
}

export function showToast(message: string, type: ToastType = "info") {
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("roombeacon:toast", {
        detail: {
          id: Math.random().toString(36).substring(2, 9),
          message,
          type,
        },
      })
    );
  }
}
