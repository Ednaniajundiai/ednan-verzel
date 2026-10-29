import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { homeFor, useAuth, type Role } from '../auth/AuthContext';

type Field = 'username' | 'password' | 'role';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role | ''>('');
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function validate(): Partial<Record<Field, string>> {
    const found: Partial<Record<Field, string>> = {};
    if (!/^[A-Za-z0-9_-]{3,32}$/.test(username.trim())) found.username = 'Use de 3 a 32 letras, números, _ ou -.';
    if (password.length < 8) found.password = 'A senha precisa de ao menos 8 caracteres.';
    if (!role) found.role = 'Escolha se você quer vender ou comprar.';
    return found;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const found = validate();
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length || !role) return;
    setBusy(true);
    try {
      const user = await register({ username: username.trim(), password, role });
      navigate(homeFor(user.role), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) {
        const server: Partial<Record<Field, string>> = {};
        for (const [field, msgs] of Object.entries(err.fieldErrors)) server[field as Field] = msgs[0];
        setErrors(server);
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Não foi possível criar a conta. Tente de novo.');
      }
      setBusy(false);
    }
  }

  const err = (field: Field) =>
    errors[field] ? (
      <p className="field-error" id={`reg-${field}-error`}>
        {errors[field]}
      </p>
    ) : null;

  return (
    <section className="card narrow">
      <h1>Criar conta</h1>
      <form className="stack" onSubmit={onSubmit} noValidate>
        <fieldset className="field" aria-describedby={errors.role ? 'reg-role-error' : undefined}>
          <legend>Como você vai usar a casa?</legend>
          <div className="choice">
            <label>
              <input type="radio" name="role" value="auctioneer" checked={role === 'auctioneer'} onChange={() => setRole('auctioneer')} />
              Quero vender (leiloeiro)
            </label>
            <label>
              <input type="radio" name="role" value="bidder" checked={role === 'bidder'} onChange={() => setRole('bidder')} />
              Quero comprar (licitante)
            </label>
          </div>
          <span className="muted">O papel fica fixo na conta.</span>
          {err('role')}
        </fieldset>
        <div className="field">
          <label htmlFor="reg-username">Usuário</label>
          <input
            id="reg-username"
            autoComplete="username"
            autoCapitalize="none"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            aria-invalid={!!errors.username}
          />
          <span className="muted">Letras, números, _ e -. É com ele que você entra.</span>
          {err('username')}
        </div>
        <div className="field">
          <label htmlFor="reg-password">Senha</label>
          <input
            id="reg-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
          />
          {err('password')}
        </div>
        {formError && (
          <p className="notice error" role="alert">
            {formError}
          </p>
        )}
        <button className="primary" type="submit" disabled={busy}>
          Criar conta
        </button>
      </form>
      <p className="muted">
        Já tem conta? <Link to="/entrar">Entrar</Link>
      </p>
    </section>
  );
}
