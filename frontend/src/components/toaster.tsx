import "./toaster.css";
import { Toaster as SonnerToaster } from "sonner";

interface ToasterProps {
  appearance: "light" | "dark";
}

export function Toaster({ appearance }: ToasterProps) {
  return (
    <SonnerToaster
      position="bottom-center"
      closeButton
      theme={appearance}
      className="toaster__viewport"
    />
  );
}
