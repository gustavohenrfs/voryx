export type User = { id: number; email: string; name: string; role: "admin" | "partner"; disabled: boolean };

export type AccountStatus = "online" | "offline" | "dead" | "connecting";

export type Account = {
  id: number;
  label: string | null;
  phone: string;
  display_name: string | null;
  status: AccountStatus;
  dead_reason: string | null;
  last_seen_at: string | null;
  created_at: string;
};

export type ChannelStatus = "ok" | "sem_acesso" | "conta_caida";

export type Channel = {
  id: number;
  title: string;
  username: string | null;
  kind: "channel" | "supergroup" | "group";
  member_count: number | null;
  status: ChannelStatus;
  join_mode: "auto" | "manual";
  manager_account_id: number | null;
  pending_count: number;
  last_synced_at: string | null;
};

export type ChannelDetail = Channel & {
  admins: { tg_user_id: number; name: string; rights: Record<string, boolean> }[];
};

export type Dialog = { chat_id: number; title: string; username: string | null; kind: string; member_count: number | null };

export type JoinRequest = {
  id: number;
  tg_user_id: number;
  name: string;
  username: string | null;
  requested_at: string;
  status: "pending" | "approved" | "rejected";
  decided_by: string | null;
  decided_at: string | null;
  queued: boolean;
};

export type Member = { user_id: number; name: string; username: string | null };

export type PostStatus = "scheduled" | "sending" | "sent" | "failed" | "canceled";

export type Post = {
  id: number;
  account_id: number | null;
  channel_id: number | null;
  text: string;
  run_at: string;
  status: PostStatus;
  error: string | null;
  media: { id: number; mime: string; size: number }[];
  sent_message_ids: number[] | null;
  finished_at: string | null;
  created_at: string;
};

export type LogEntry = {
  id: number;
  action: string;
  account_id: number | null;
  channel_id: number | null;
  target: string | null;
  result: string;
  detail: string | null;
  created_at: string;
};

export const accountName = (a: Account) => a.label || a.display_name || a.phone;
