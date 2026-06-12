interface Props {
  title: string;
  onShowAll?: () => void;
}

export function SectionHeader({ title, onShowAll }: Props) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "16px 16px 8px" }}>
      <span style={{ fontSize: 17, fontWeight: 600, color: "var(--tg-theme-text-color)" }}>
        {title}
      </span>
      {onShowAll && (
        <span
          style={{ fontSize: 15, color: "var(--tg-theme-link-color)", cursor: "pointer" }}
          onClick={onShowAll}
        >
          Показать все
        </span>
      )}
    </div>
  );
}
