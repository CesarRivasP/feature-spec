export function validate(p: any) {
  if (typeof p.user_id !== "string") throw new Error("user_id");
  if (typeof p.amount !== "number") throw new Error("amount");
}
