export type AccountRole = "business" | "risk" | "leadership";
export interface AuthenticatedAccount {
  accountId: string;
  username: string;
  displayName: string;
  role: AccountRole;
}
