import { useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import { parseBRLToCents } from '../../lib/money';
import { CatalogSearch, type Jersey } from './CatalogSearch';

const SIZES = ['PP', 'P', 'M', 'G', 'GG', 'XGG'] as const;
const CONDITIONS = [
  { value: 'nova_com_etiqueta', label: 'Nova com etiqueta' },
  { value: 'nova', label: 'Nova' },
  { value: 'usada', label: 'Usada' },
] as const;

type Field = 'title' | 'size' | 'condition' | 'starts_at' | 'ends_at' | 'starting_price_cents' | 'min_increment_cents';
type Errors = Partial<Record<Field, string>>;

/** Título sugerido (FR-011): "Camisa {time} {temporada} {tipo}". */
export function suggestTitle(j: Jersey): string {
  return ['Camisa', j.team_name, j.season, j.kind_label?.toLowerCase()].filter(Boolean).join(' ') || j.title;
}

const START_TOLERANCE_MS = 60_000;

/**
 * Formulário do lote. A validação espelha a FR-012 para dar retorno rápido;
 * o servidor continua sendo a autoridade (e decide "passado" pelo relógio do banco).
 */
export function LotForm({ jersey, onCreated }: { jersey: Jersey; onCreated: (lotId: string) => void }) {
  const [title, setTitle] = useState(() => suggestTitle(jersey));
  const [size, setSize] = useState('');
  const [condition, setCondition] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [startPrice, setStartPrice] = useState('');
  const [increment, setIncrement] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function validate(): { errors: Errors; body?: Record<string, unknown> } {
    const found: Errors = {};
    if (!title.trim()) found.title = 'Informe o título.';
    if (!size) found.size = 'Escolha um tamanho.';
    if (!condition) found.condition = 'Escolha o estado de conservação.';

    const now = Date.now();
    const start = startsAt ? new Date(startsAt) : null;
    const end = endsAt ? new Date(endsAt) : null;
    if (start && Number.isNaN(start.getTime())) found.starts_at = 'Data e hora inválidas.';
    else if (start && start.getTime() < now - START_TOLERANCE_MS) found.starts_at = 'O início não pode estar no passado.';
    if (!end || Number.isNaN(end.getTime())) found.ends_at = 'Informe o fim.';
    else if (end.getTime() <= (start?.getTime() ?? now)) found.ends_at = 'O fim deve ser depois do início.';

    const startCents = parseBRLToCents(startPrice);
    const incrementCents = parseBRLToCents(increment);
    if (startCents === null) found.starting_price_cents = 'Informe um valor válido em reais.';
    else if (startCents <= 0) found.starting_price_cents = 'O lance inicial deve ser maior que zero.';
    if (incrementCents === null) found.min_increment_cents = 'Informe um valor válido em reais.';
    else if (incrementCents <= 0) found.min_increment_cents = 'O incremento deve ser maior que zero.';

    if (Object.keys(found).length) return { errors: found };
    return {
      errors: found,
      body: {
        item_id: jersey.id,
        title: title.trim(),
        size,
        condition,
        ...(start ? { starts_at: start.toISOString() } : {}),
        ends_at: end!.toISOString(),
        starting_price_cents: startCents,
        min_increment_cents: incrementCents,
      },
    };
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const { errors: found, body } = validate();
    setErrors(found);
    if (!body) return;
    setBusy(true);
    try {
      const res = await api<{ id: string }>('/auctioneer/lots', { body });
      onCreated(res.id);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) {
        const server: Errors = {};
        for (const [field, msgs] of Object.entries(err.fieldErrors)) {
          if (field === 'item_id') setFormError(msgs[0] ?? 'Escolha uma camisa.');
          else server[field as Field] = msgs[0];
        }
        setErrors(server);
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Não foi possível publicar o lote. Tente de novo.');
      }
    } finally {
      setBusy(false);
    }
  }

  const field = (name: Field, label: string, control: (props: FieldProps) => ReactNode, hint?: string) => {
    const id = `lot-${name}`;
    const errorId = `${id}-error`;
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        {control({ id, 'aria-invalid': !!errors[name], 'aria-describedby': errors[name] ? errorId : undefined })}
        {hint && !errors[name] && <span className="muted">{hint}</span>}
        {errors[name] && (
          <p className="field-error" id={errorId}>
            {errors[name]}
          </p>
        )}
      </div>
    );
  };

  return (
    <form className="stack" onSubmit={onSubmit} noValidate aria-label="Dados do lote">
      {field('title', 'Título', (p) => (
        <input {...p} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
      ))}
      <div className="row">
        {field('size', 'Tamanho', (p) => (
          <select {...p} value={size} onChange={(e) => setSize(e.target.value)}>
            <option value="">Escolha…</option>
            {SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ))}
        {field('condition', 'Estado de conservação', (p) => (
          <select {...p} value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="">Escolha…</option>
            {CONDITIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        ))}
      </div>
      <div className="row">
        {field(
          'starts_at',
          'Início',
          (p) => <input {...p} type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />,
          'Vazio = começa agora.',
        )}
        {field('ends_at', 'Fim', (p) => (
          <input {...p} type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
        ))}
      </div>
      <div className="row">
        {field('starting_price_cents', 'Lance inicial (R$)', (p) => (
          <input {...p} inputMode="decimal" placeholder="150,00" value={startPrice} onChange={(e) => setStartPrice(e.target.value)} />
        ))}
        {field('min_increment_cents', 'Incremento mínimo (R$)', (p) => (
          <input {...p} inputMode="decimal" placeholder="10,00" value={increment} onChange={(e) => setIncrement(e.target.value)} />
        ))}
      </div>
      {formError && (
        <p className="notice error" role="alert">
          {formError}
        </p>
      )}
      <button className="primary" type="submit" disabled={busy}>
        Publicar lote
      </button>
    </form>
  );
}

interface FieldProps {
  id: string;
  'aria-invalid': boolean;
  'aria-describedby'?: string;
}

/** Rota /painel/novo: escolher a camisa no catálogo e preencher o lote. */
export function NewLotPage() {
  const navigate = useNavigate();
  const [jersey, setJersey] = useState<Jersey | null>(null);

  return (
    <section className="stack">
      <div className="page-head">
        <h1>Novo lote</h1>
      </div>
      <div className="card stack">
        <h2>1. Escolha a camisa</h2>
        <CatalogSearch onSelect={setJersey} selectedId={jersey?.id} />
      </div>
      <div className="card stack">
        <h2>2. Dados do lote</h2>
        {jersey ? (
          <>
            <div className="row">
              {jersey.image_url && <img className="thumb" style={{ maxWidth: 120 }} src={jersey.image_url} alt="" />}
              <p className="muted">
                {jersey.title}
                <br />
                {[jersey.team_name, jersey.league, jersey.season, jersey.kind_label].filter(Boolean).join(' · ')}
              </p>
            </div>
            <LotForm
              key={jersey.id}
              jersey={jersey}
              onCreated={(id) => navigate('/painel', { state: { created: id } })}
            />
          </>
        ) : (
          <p className="muted">Escolha uma camisa acima para preencher o lote.</p>
        )}
      </div>
    </section>
  );
}
