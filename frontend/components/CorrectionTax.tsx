export function CorrectionTax({ value }: { value: number }) {
  return (
    <div className="text-center">
      <p className="text-4xl font-bold text-indigo-600">{value.toFixed(2)}</p>
      <p className="text-sm text-gray-500 mt-1">avg extra iterations before pass</p>
      <p className="text-xs text-gray-400 mt-0.5">0 = first-try pass every time</p>
    </div>
  );
}
