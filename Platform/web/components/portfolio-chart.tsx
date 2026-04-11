"use client";

import {
  LineChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { format } from 'date-fns';
import React from 'react';
import { useMemo } from 'react';

interface ExtendedChartPoint {
  ts: string;
  equity: number;
  drawdown: number;
  benchmark?: number;
}

interface PortfolioChartProps {
  data: ExtendedChartPoint[];
  height?: number;
  windowSize?: string;
  title?: string;
  subtitle?: string;
}

export function PortfolioChart({
  data,
  height = 250,
  windowSize = '80',
  title = 'Portfolio Performance',
  subtitle = 'Equity curve vs benchmark (realized PnL)',
}: PortfolioChartProps) {
  const chartData = useMemo(() => {
    return data.map((point, idx) => ({
      ...point,
      benchmark: point.equity * 1.01 + (Math.sin(idx / 10) * point.equity * 0.005), // Mock benchmark
    }));
  }, [data]);




interface TooltipPayloadItem {
  payload: ExtendedChartPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

const CustomTooltipWithProps = ({ active, payload }: CustomTooltipProps) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload;
      return (
        <div className="rounded-lg bg-white p-3 shadow-lg border border-gray-200 dark:bg-gray-900 dark:border-gray-800 dark:text-gray-100">
          <p className="font-semibold text-gray-900 dark:text-white">{format(new Date(point.ts), 'MMM dd yyyy HH:mm')}</p>
          <div className="mt-1 space-y-1 text-sm">
            <p><span className="font-mono text-brand-600">Equity:</span> {point.equity.toFixed(2)} USDT</p>
            <p><span className="font-mono text-gray-600">Benchmark:</span> {point.benchmark?.toFixed(2)} USDT</p>
            <p><span className="font-mono text-orange-600">Drawdown:</span> {point.drawdown.toFixed(2)} USDT</p>
            {data.length > 1 && (
              <p><span className="font-mono text-brand-600">Δ:</span> {((point.equity - data[data.length - 2]?.equity || 0).toFixed(2))} USDT</p>
            )}
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
          <p className="mt-1 text-xs text-gray-400">Window: {windowSize} points | {chartData.length} data points</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#465fff" stopOpacity={0.4}/>
              <stop offset="80%" stopColor="#465fff" stopOpacity={0.05}/>
            </linearGradient>
            <linearGradient id="benchmarkGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6b7280" stopOpacity={0.3}/>
              <stop offset="100%" stopColor="#6b7280" stopOpacity={0.05}/>
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--gray-200))" />
          <XAxis
            dataKey="ts"
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => format(new Date(value), 'MMM dd')}
            tickMargin={12}
            fontSize={12}
            height={60}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tickMargin={12}
            fontSize={12}
          />
          <Tooltip
            content={({ active, payload }) => (
              <CustomTooltipWithProps active={active} payload={payload as unknown as TooltipPayloadItem[]} />
            )}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="#465fff"
            strokeWidth={3}
            fillOpacity={1}
            fill="url(#equityGradient)"
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#6b7280"
            strokeWidth={2}
            strokeDasharray="5 5"
            name="Benchmark"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
