let isAuthenticationRedirecting = false;

export function handleAuthenticationFailure(): void {
  if (typeof window === "undefined" || isAuthenticationRedirecting) return;
  isAuthenticationRedirecting = true;
  window.location.reload();
}
