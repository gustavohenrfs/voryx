import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/Toast";
import type { Account, Channel } from "@/lib/types";
import { PostForm } from "./PostForm";

const apiMock = vi.fn();
const uploadMock = vi.fn();
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: (...a: unknown[]) => apiMock(...a),
  upload: (...a: unknown[]) => uploadMock(...a),
}));

const accounts: Account[] = [
  { id: 1, label: "Ana", phone: "+1", display_name: null, status: "online", dead_reason: null, last_seen_at: null, created_at: "" },
];
const channels: Channel[] = [
  { id: 3, title: "Prévias VIP", username: null, kind: "channel", member_count: 1, status: "ok", join_mode: "manual",
    manager_account_id: 1, pending_count: 0, last_synced_at: null },
];

function setup() {
  render(
    <ToastProvider>
      <PostForm accounts={accounts} channels={channels} onSaved={() => {}} />
    </ToastProvider>,
  );
}

describe("PostForm", () => {
  beforeEach(() => {
    apiMock.mockReset();
    uploadMock.mockReset();
    apiMock.mockResolvedValue({ id: 9 });
    uploadMock.mockResolvedValue({ id: 50, mime: "image/jpeg", size: 3 });
  });

  it("blocks a caption over 1024 characters when there is media", async () => {
    const user = userEvent.setup();
    setup();
    const file = new File(["abc"], "a.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText("Fotos e vídeos"), file);
    await screen.findByText("a.jpg");
    fireEvent.change(screen.getByLabelText("Texto"), { target: { value: "x".repeat(1025) } });
    expect(screen.getByText("1025 / 1024")).toHaveClass("text-[#ff9c92]");
    expect(screen.getByRole("button", { name: "Agendar" })).toBeDisabled();
  });

  it("sends run_at with the São Paulo offset", async () => {
    const user = userEvent.setup();
    setup();
    fireEvent.change(screen.getByLabelText("Texto"), { target: { value: "oi" } });
    fireEvent.change(screen.getByLabelText("Dia"), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("Hora"), { target: { value: "20:00" } });
    await user.click(screen.getByRole("button", { name: "Agendar" }));
    expect(apiMock).toHaveBeenCalledWith("/posts", {
      json: { account_id: 1, channel_id: 3, text: "oi", media_ids: [], run_at: "2026-11-10T20:00:00-03:00", post_now: false },
    });
  });

  it("rejects a file over the upload limit before sending it", async () => {
    const user = userEvent.setup();
    setup();
    const big = new File(["x"], "longo.mp4", { type: "video/mp4" });
    Object.defineProperty(big, "size", { value: 600 * 1024 * 1024 });
    await user.upload(screen.getByLabelText("Fotos e vídeos"), big);
    expect(await screen.findByText(/longo\.mp4 passa de 500 MB/)).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("post now sends post_now without run_at", async () => {
    const user = userEvent.setup();
    setup();
    fireEvent.change(screen.getByLabelText("Texto"), { target: { value: "agora" } });
    await user.click(screen.getByRole("button", { name: "Postar agora" }));
    expect(apiMock.mock.calls[0][1].json).toMatchObject({ post_now: true, run_at: null, text: "agora" });
  });
});
