"use client";

import { format } from "date-fns";
import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ExtendedChartPoint {
  ts: string;
  ts_ms?: number;
  equity: number;
  drawdown: number;
  drawdown_pct?: number | null;
  pnl_usdt?: number | null;
  pnl_pct?: number | null;
  run_key?: string | null;
  samples?: number;
}

interface PortfolioChartProps {
  data: ExtendedChartPoint[];
  height?: number;
  caption?: string;
  title?: string;
  subtitle?: string;
}

interface TooltipPayloadItem {
  payload: ExtendedChartPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)}%`;
}

function formatDate(value: string | number, pattern: string): string {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return format(dt, pattern);
}

export function PortfolioChart({
  data,
  height = 250,
  caption = "Portfolio equity history",
  title = "Portfolio Performance",
  subtitle = "Account equity from run heartbeat data",
}: PortfolioChartProps) {
  const chartData = useMemo(
    () =>
      data
        .map((point) => {
          const tsMs = new Date(point.ts).getTime();
          return { ...point, ts_ms: Number.isFinite(tsMs) ? tsMs : undefined };
        })
        .filter((point) => point.ts_ms !== undefined),
    [data],
  );

  const tickFormat = useMemo(() => {
    if (chartData.length < 2) return "MMM dd HH:mm";
    const first = chartData[0].ts_ms ?? 0;
    const last = chartData[chartData.length - 1].ts_ms ?? 0;
    const spanHours = Number.isFinite(first) && Number.isFinite(last) ? Math.abs(last - first) / 3_600_000 : 0;
    if (spanHours <= 48) return "HH:mm";
    if (spanHours <= 24 * 45) return "MMM dd";
    return "MMM yyyy";
  }, [chartData]);

  const CustomTooltipWithProps = ({ active, payload }: CustomTooltipProps) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload;
      return (
        <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100">
          <p className="font-semibold text-gray-900 dark:text-white">{formatDate(point.ts, "MMM dd yyyy HH:mm")}</p>
          <div className="mt-1 space-y-1 text-sm">
            <p><span className="font-mono text-brand-600">Equity:</span> {formatMoney(point.equity)} USDT</p>
            <p><span className="font-mono text-success-600">Change:</span> {formatMoney(point.pnl_usdt)} USDT ({formatPct(point.pnl_pct)})</p>
            <p><span className="font-mono text-orange-600">Drawdown:</span> {formatMoney(point.drawdown)} USDT ({formatPct(point.drawdown_pct)})</p>
            {point.run_key ? <p><span className="font-mono text-gray-600">Run:</span> {point.run_key}</p> : null}
            {point.samples && point.samples > 1 ? <p><span className="font-mono text-gray-600">Samples:</span> {point.samples}</p> : null}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
          <p className="mt-1 text-xs text-gray-400">{caption} | {chartData.length} data points</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#465fff" stopOpacity={0.4} />
              <stop offset="80%" stopColor="#465fff" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="ts_ms"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => formatDate(String(value), tickFormat)}
            tickMargin={12}
            fontSize={12}
            height={60}
          />
          <YAxis
            yAxisId="equity"
            tickLine={false}
            axisLine={false}
            tickMargin={12}
            fontSize={12}
            domain={["auto", "auto"]}
            tickFormatter={(value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          />
          <Tooltip
            content={({ active, payload }) => (
              <CustomTooltipWithProps active={active} payload={payload as unknown as TooltipPayloadItem[]} />
            )}
          />
          <Area
            type="monotone"
            dataKey="equity"
            yAxisId="equity"
            name="Equity"
            stroke="#465fff"
            strokeWidth={3}
            fillOpacity={1}
            fill="url(#equityGradient)"
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
