import { QueryClientProvider } from "@tanstack/react-query";
import { NotchToaster } from "notch-toast";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { router } from "./app/router";
import { queryClient } from "./lib/query";
import { initSound } from "./lib/sound";
import "./styles/index.css";
import { BodyScrollbars, TooltipProvider } from "./ui";

initSound();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BodyScrollbars />
        <RouterProvider router={router} />
        <NotchToaster position="top-center" mode="attached" animation="fluid" />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
