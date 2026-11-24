import { useEffect } from "react";

export function Modal({ titulo, onClose, children, largo, rodape }) {
  useEffect(() => {
    const esc = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", esc);
      document.body.style.overflow = "";
    };
  }, [onClose]);
  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${largo ? "largo" : ""}`} role="dialog" aria-modal="true" aria-label={titulo}>
        <header className="modal-topo">
          <h2>{titulo}</h2>
          <button className="btn-icone" onClick={onClose} aria-label="Fechar">×</button>
        </header>
        <div className="modal-corpo">{children}</div>
        {rodape && <footer className="modal-rodape">{rodape}</footer>}
      </div>
    </div>
  );
}

export const Carregando = ({ texto = "Carregando…" }) => (
  <div className="carregando"><span className="giro" />{texto}</div>
);

export const Erro = ({ erro, onRetry }) =>
  erro ? (
    <div className="aviso erro">
      Não deu certo: {String(erro.message || erro)}
      {onRetry && <button className="btn-link" onClick={onRetry}>Tentar de novo</button>}
    </div>
  ) : null;

export const Chip = ({ children, tom = "" }) => <span className={`chip ${tom}`}>{children}</span>;

export function Barra({ valor }) {
  const v = Math.max(0, Math.min(100, valor ?? 0));
  return <div className="barra"><div style={{ width: `${v}%` }} /></div>;
}

export function Voltar({ para, children }) {
  return <a className="voltar" href={para}>← {children}</a>;
}
