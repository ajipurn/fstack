import { toast } from "notch-toast";
import { play } from "./sound";

/** Toasts with matching sounds. notch-toast is latest-wins, so keep titles short. */
export const notify = {
  success(title: string) {
    play("success");
    return toast.success(title);
  },
  error(title: string) {
    play("error");
    return toast.error(title.length > 120 ? `${title.slice(0, 117)}…` : title);
  },
  info(title: string) {
    return toast.info(title);
  },
  loading(title: string, id?: string) {
    return toast.loading(title, { id });
  },
  promise<T>(promise: Promise<T>, labels: { loading: string; success: string | ((value: T) => string); error?: string }) {
    return toast.promise(promise, {
      loading: labels.loading,
      success: (value) => {
        play("success");
        return typeof labels.success === "function" ? labels.success(value) : labels.success;
      },
      error: (reason) => {
        play("error");
        return labels.error ?? (reason instanceof Error ? reason.message : "Something went wrong.");
      },
    });
  },
  dismiss: toast.dismiss,
};
