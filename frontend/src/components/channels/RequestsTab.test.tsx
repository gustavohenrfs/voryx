import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/Toast";
import type { ChannelDetail } from "@/lib/types";
import { RequestsTab } from "./RequestsTab";

const apiMock = vi.fn();
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: (...a: unknown[]) => apiMock(...a) }));

const channel: ChannelDetail = {
  id: 3, title: "Prévias VIP", username: null, kind: "channel", member_count: 10, status: "ok", join_mode: "manual",
  manager_account_id: 1, pending_count: 2, last_synced_at: null, admins: [],
};
const pending = [
  { id: 11, tg_user_id: 100, name: "Carlos", username: null, requested_at: "2026-11-10T12:00:00Z", status: "pending", decided_by: null, decided_at: null, queued: false },
  { id: 12, tg_user_id: 101, name: "Bruno", username: "bru", requested_at: "2026-11-10T12:01:00Z", status: "pending", decided_by: null, decided_at: null, queued: false },
];

function setup() {
  apiMock.mockImplementation(async (...args: unknown[]) => (String(args[0]).includes("/requests?") ? pending : { queued: true }));
  render(<ToastProvider><RequestsTab channel={channel} onChannelChange={() => {}} /></ToastProvider>);
}

describe("RequestsTab", () => {
  beforeEach(() => apiMock.mockReset());

  it("approve-all asks for confirmation before calling the API", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: "Aprovar todos (2)" }));
    expect(apiMock).not.toHaveBeenCalledWith("/channels/3/requests/approve-all", expect.anything());
    await user.click(screen.getByRole("button", { name: "Aprovar 2 pedidos" }));
    expect(apiMock).toHaveBeenCalledWith("/channels/3/requests/approve-all", { method: "POST" });
  });

  it("approving one request calls its endpoint", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: "Aprovar Carlos" }));
    expect(apiMock).toHaveBeenCalledWith("/channels/3/requests/11/approve", { method: "POST" });
  });

  it("switching to automatic patches the channel", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("radio", { name: /Automático/ }));
    expect(apiMock).toHaveBeenCalledWith("/channels/3", { method: "PATCH", json: { join_mode: "auto" } });
  });
});
