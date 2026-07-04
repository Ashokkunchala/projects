export const OWNER_NAME     = import.meta.env.VITE_OWNER_NAME ?? "AI Cloud Cost Detective"
export const OWNER_LINKEDIN = import.meta.env.VITE_OWNER_LINKEDIN ?? ""
export const OWNER_EMAIL    = import.meta.env.VITE_OWNER_EMAIL ?? ""
export const OWNER_GITHUB   = import.meta.env.VITE_OWNER_GITHUB ?? ""

export async function validateOwnership(): Promise<void> {}
