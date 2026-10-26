type BrandLogoProps = {
  compact?: boolean;
  className?: string;
};

export function BrandLogo({ compact = false, className = "" }: BrandLogoProps) {
  const classes = ["brand-lockup", compact ? "compact" : "", className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <img className="brand-logo" src="/branding/xuanzhi-logo.png" alt="" aria-hidden="true" />
      <span className="brand-name">玄知大模型</span>
    </div>
  );
}
