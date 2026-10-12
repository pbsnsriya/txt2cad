import { useEffect, useMemo, useState } from 'react';
import type { Analysis } from '../api/client';
import { Card, EmptyState, Skeleton } from '../ui/Surface';

const KEY = 'txt2cad.rates.v1';

function readRates(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '{}'); } catch { return {}; }
}

/** Quantities from the geometry. The app has no prices: type your own rate per unit and the totals follow. */
export function QuantitiesTab({ analysis, loading }: { analysis: Analysis | null; loading: boolean }) {
  const [rates, setRates] = useState<Record<string, string>>(readRates);
  const [currency, setCurrency] = useState(() => { try { return localStorage.getItem(KEY + '.cur') ?? 'Rs'; } catch { return 'Rs'; } });
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(rates)); localStorage.setItem(KEY + '.cur', currency); } catch { /* storage may be blocked */ } }, [rates, currency]);
  const rows = analysis?.quantities.rows ?? [];
  const total = useMemo(() => rows.reduce((s, r) => s + r.qty * (Number(rates[r.item]) || 0), 0), [rows, rates]);
  if (loading) return <div className="p-4"><Skeleton className="h-60" /></div>;
  if (!analysis) return <EmptyState title="Build something to measure it here." />;
  const groups = [...new Set(rows.map((r) => r.group))];
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">Quantities and cost</h2>
          <p className="text-sm text-muted">Measured from the model. Prices are not included: enter your own rate per unit and the cost fills in.</p>
        </div>
        <label className="flex items-center gap-2 text-sm">Currency symbol
          <input value={currency} maxLength={4} onChange={(e) => setCurrency(e.target.value)} className="h-8 w-16 rounded-md border border-input bg-surface px-2" />
        </label>
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <caption className="sr-only">Quantities by element group</caption>
            <thead><tr className="text-xs text-muted">
              <th scope="col" className="px-3 py-2 text-left">Item</th><th scope="col" className="px-3 py-2 text-right">Quantity</th>
              <th scope="col" className="px-3 py-2 text-left">Unit</th><th scope="col" className="px-3 py-2 text-right">Rate per unit</th><th scope="col" className="px-3 py-2 text-right">Cost</th>
            </tr></thead>
            {groups.map((g) => (
              <tbody key={g}>
                <tr><th colSpan={5} scope="colgroup" className="bg-surface-sunken px-3 py-1 text-left text-xs font-medium text-muted">{g}</th></tr>
                {rows.filter((r) => r.group === g).map((r) => (
                  <tr key={r.item} className="border-t border-border">
                    <td className="px-3 py-2">{r.item}{r.note && <span className="block text-xs text-muted">{r.note}</span>}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{r.qty}</td>
                    <td className="px-3 py-2">{r.unit}</td>
                    <td className="px-3 py-2 text-right">
                      <input aria-label={`Rate per ${r.unit} for ${r.item}`} inputMode="decimal" value={rates[r.item] ?? ''} placeholder="0"
                        onChange={(e) => setRates({ ...rates, [r.item]: e.target.value.replace(/[^0-9.]/g, '') })}
                        className="h-8 w-24 rounded-md border border-input bg-surface px-2 text-right tabular-nums" />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{(Number(rates[r.item]) || 0) ? `${currency} ${(r.qty * Number(rates[r.item])).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : ''}</td>
                  </tr>
                ))}
              </tbody>
            ))}
            <tfoot><tr className="border-t border-border font-medium">
              <td colSpan={4} className="px-3 py-2 text-right">Total of the rows you priced</td>
              <td className="px-3 py-2 text-right tabular-nums">{currency} {total.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
            </tr></tfoot>
          </table>
        </Card>
        <Card variant="sunken" className="text-sm"><h3 className="mb-1 font-medium">Rooms</h3>
          <ul className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">{analysis.quantities.rooms.map((r, i) => <li key={i} className="flex justify-between"><span>{r.name} <span className="text-muted">{r.level}</span></span><span className="tabular-nums">{r.area_m2} m2</span></li>)}</ul>
        </Card>
      </div>
    </div>
  );
}
