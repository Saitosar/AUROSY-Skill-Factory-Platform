import type { ReactNode } from "react";

export type ValidateBannerProps =
  | {
      variant: "error";
      title: string;
      errors: string[];
      /** When set, rows are clickable for emphasis; use with selectedErrorIndex / onSelectError */
      selectable?: boolean;
      selectedErrorIndex?: number | null;
      onSelectError?: (index: number) => void;
      copyPathAriaLabel?: string;
    }
  | { variant: "success"; children: ReactNode }
  | { variant: "warning"; children: ReactNode };

/** First whitespace-separated token is treated as JSON Schema instance path (AJV). */
export function splitValidationErrorLine(line: string): { path: string; rest: string } {
  const trimmed = line.trim();
  const space = trimmed.indexOf(" ");
  if (space === -1) return { path: trimmed, rest: "" };
  return { path: trimmed.slice(0, space), rest: trimmed.slice(space + 1) };
}

export function ValidateBanner(props: ValidateBannerProps) {
  if (props.variant === "error") {
    const sel = props.selectable;
    return (
      <div className="validate-banner err" role="alert" aria-live="polite">
        <div className="validate-banner-title">{props.title}</div>
        <ul className="validation-errors">
          {props.errors.map((line, i) => {
            const { path, rest } = splitValidationErrorLine(line);
            const display = rest ? `${path} ${rest}` : path;
            const isSelected = props.selectedErrorIndex === i;
            if (sel && props.onSelectError) {
              return (
                <li key={i} className={isSelected ? "validation-error-selected validation-error-li" : "validation-error-li"}>
                  <button
                    type="button"
                    className="validation-error-row"
                    onClick={() => props.onSelectError!(i)}
                    aria-pressed={isSelected}
                  >
                    {display}
                  </button>
                  {path && path !== "/" && (
                    <button
                      type="button"
                      className="secondary validation-error-copy-path"
                      title={props.copyPathAriaLabel}
                      aria-label={props.copyPathAriaLabel}
                      onClick={(e) => {
                        e.stopPropagation();
                        void navigator.clipboard.writeText(path);
                      }}
                    >
                      ⧉
                    </button>
                  )}
                </li>
              );
            }
            return <li key={i}>{line}</li>;
          })}
        </ul>
      </div>
    );
  }
  if (props.variant === "success") {
    return <p className="ok validate-banner-success">{props.children}</p>;
  }
  return (
    <div className="warn-banner" role="status">
      {props.children}
    </div>
  );
}
