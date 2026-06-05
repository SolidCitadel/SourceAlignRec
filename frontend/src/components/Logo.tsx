interface LogoProps {
  size?: number;
}

export function Logo({ size = 26 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" aria-hidden="true">
      <circle cx="13" cy="13" r="12" fill="var(--color-primary)" />
      <path
        d="M5 16 Q13 6 21 16"
        stroke="#fff"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="13" cy="9" r="1.6" fill="#fff" />
    </svg>
  );
}
