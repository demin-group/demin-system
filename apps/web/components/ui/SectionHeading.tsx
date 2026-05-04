type Props = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  centered?: boolean;
};

export default function SectionHeading({ title, subtitle, centered = false }: Props) {
  return (
    <div className={centered ? "text-center max-w-2xl mx-auto" : "max-w-3xl"}>
      <h2 className="relative inline-block text-3xl md:text-4xl font-semibold tracking-tight text-[var(--ink-primary)]">
        {title}
        <span
          aria-hidden="true"
          className="absolute -bottom-3 left-0 h-[2px] w-12 bg-[var(--accent)]"
        />
      </h2>
      {subtitle && (
        <p className="mt-8 text-base md:text-lg text-[var(--ink-secondary)] leading-relaxed">
          {subtitle}
        </p>
      )}
    </div>
  );
}
