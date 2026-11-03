import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { LoginWizard } from "./LoginWizard";

const apiMock = vi.fn();
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: (...a: unknown[]) => apiMock(...a) }));

async function fillStart(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Número com DDI"), "+5511999990000");
  await user.type(screen.getByLabelText("api_id"), "12345");
  await user.type(screen.getByLabelText("api_hash"), "0123456789abcdef0123456789abcdef");
  await user.click(screen.getByRole("button", { name: "Enviar código" }));
}

describe("LoginWizard", () => {
  beforeEach(() => apiMock.mockReset());

  it("asks for the 2FA password when the API says needs_password", async () => {
    const user = userEvent.setup();
    apiMock.mockResolvedValueOnce({ login_id: "L1" }).mockResolvedValueOnce({ status: "needs_password" });
    render(<LoginWizard onDone={() => {}} />);
    await fillStart(user);
    await user.type(await screen.findByLabelText("Código recebido no Telegram"), "12345");
    await user.click(screen.getByRole("button", { name: "Confirmar código" }));
    expect(await screen.findByLabelText("Senha de verificação em duas etapas")).toBeInTheDocument();
    expect(apiMock).toHaveBeenNthCalledWith(2, "/accounts/login/code", { json: { login_id: "L1", code: "12345" } });
  });

  it("shows the API error for a wrong code and stays on the code step", async () => {
    const user = userEvent.setup();
    apiMock.mockResolvedValueOnce({ login_id: "L1" }).mockRejectedValueOnce(new ApiError(400, "código inválido"));
    render(<LoginWizard onDone={() => {}} />);
    await fillStart(user);
    await user.type(await screen.findByLabelText("Código recebido no Telegram"), "00000");
    await user.click(screen.getByRole("button", { name: "Confirmar código" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("código inválido");
    expect(screen.getByLabelText("Código recebido no Telegram")).toBeInTheDocument();
  });

  it("calls onDone with the account after success and sends account_id on relogin", async () => {
    const user = userEvent.setup();
    const done = vi.fn();
    const account = { id: 7, status: "online" };
    apiMock.mockResolvedValueOnce({ login_id: "L1" }).mockResolvedValueOnce({ status: "ok", account });
    render(<LoginWizard accountId={7} onDone={done} />);
    await fillStart(user);
    await user.type(await screen.findByLabelText("Código recebido no Telegram"), "12345");
    await user.click(screen.getByRole("button", { name: "Confirmar código" }));
    await vi.waitFor(() => expect(done).toHaveBeenCalledWith(account));
    expect(apiMock.mock.calls[0][1].json.account_id).toBe(7);
  });
});
