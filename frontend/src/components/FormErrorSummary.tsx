interface Props {
  errors: Record<string, { message?: string } | undefined>;
}

export function FormErrorSummary({ errors }: Props) {
  const messages = Object.values(errors)
    .filter(Boolean)
    .map((e) => e?.message)
    .filter(Boolean) as string[];

  if (messages.length === 0) return null;

  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <p className="font-medium mb-1">Corrija os erros abaixo:</p>
      <ul className="list-disc list-inside space-y-0.5">
        {messages.map((msg, i) => (
          <li key={i}>{msg}</li>
        ))}
      </ul>
    </div>
  );
}
