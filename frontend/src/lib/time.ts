// O painel opera em horário de São Paulo. O Brasil não tem horário de verão desde 2019,
// então o offset é fixo em -03:00.
export const TZ = "America/Sao_Paulo";
const OFFSET = "-03:00";

const parts = (iso: string) => {
  const f = new Intl.DateTimeFormat("pt-BR", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const out: Record<string, string> = {};
  for (const p of f.formatToParts(new Date(iso))) out[p.type] = p.value;
  return out;
};

/** "10/11 20:00" */
export function toSaoPaulo(iso: string): string {
  const p = parts(iso);
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`;
}

/** "20:00" */
export function timeOf(iso: string): string {
  const p = parts(iso);
  return `${p.hour}:${p.minute}`;
}

/** "2026-11-10" — dia do calendário em São Paulo */
export function dayKey(iso: string): string {
  const p = parts(iso);
  return `${p.year}-${p.month}-${p.day}`;
}

/** date "2026-11-10" + time "20:00" (inputs do formulário) → ISO com offset */
export function fromSaoPauloInput(date: string, time: string): string {
  return `${date}T${time}:00${OFFSET}`;
}

/** valores iniciais dos inputs date/time a partir de um ISO */
export function toInputs(iso: string): { date: string; time: string } {
  const p = parts(iso);
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}` };
}

export function dayLabel(key: string, todayKey: string): string {
  const d = new Date(`${key}T12:00:00${OFFSET}`);
  const t = new Date(`${todayKey}T12:00:00${OFFSET}`);
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000);
  if (diff === 0) return "Hoje";
  if (diff === 1) return "Amanhã";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }).format(d);
}
