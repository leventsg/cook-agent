/**
 * LLM Statistics Dashboard Page
 * Displays usage statistics, trends, and distribution
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Clock,
  Loader2,
  RefreshCcw,
  Zap,
  TrendingUp,
  PieChart as PieChartIcon,
  Layers,
  Cpu,
} from 'lucide-react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { useAuth } from '../contexts';
import {
  getLLMStatsSummary,
  getLLMStatsTimeSeries,
  getLLMStatsDistributionByModule,
  getLLMStatsDistributionByModel,
  getLLMStatsDistributionByTool,
  getLLMStatsModules,
  getLLMStatsModels,
} from '../services/api/llmStats';
import type {
  LLMStatsSummary,
  TimeSeriesResponse,
  ModuleDistributionResponse,
  ModelDistributionResponse,
  ModuleDistribution,
  ModelDistribution,
  ToolDistribution,
  ToolDistributionResponse,
} from '../types/llmStats';

// Chart colors
const COLORS = [
  '#f97316', // orange-500
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#eab308', // yellow-500
  '#6366f1', // indigo-500
  '#14b8a6', // teal-500
];

/**
 * Stat card component
 */
interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color?: 'orange' | 'blue' | 'green' | 'red' | 'gray' | 'violet';
}

function StatCard({ title, value, subtitle, icon, color = 'orange' }: StatCardProps) {
  const colorClasses = {
    orange: 'from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 border-orange-200 dark:border-orange-800',
    blue: 'from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border-blue-200 dark:border-blue-800',
    green: 'from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 border-emerald-200 dark:border-emerald-800',
    red: 'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-800',
    gray: 'from-gray-50 to-gray-100 dark:from-gray-900/20 dark:to-gray-800/20 border-gray-200 dark:border-gray-800',
    violet: 'from-violet-50 to-violet-100 dark:from-violet-900/20 dark:to-violet-800/20 border-violet-200 dark:border-violet-800',
  };

  const iconColorClasses = {
    orange: 'text-orange-500',
    blue: 'text-blue-500',
    green: 'text-emerald-500',
    red: 'text-red-500',
    gray: 'text-gray-500',
    violet: 'text-violet-500',
  };

  return (
    <div className={`bg-gradient-to-br ${colorClasses[color]} border rounded-2xl p-4 shadow-sm min-w-0 flex-shrink-0 transition-all duration-200 hover:shadow-md hover:-translate-y-0.5`}>
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-gray-500 dark:text-gray-400 font-medium uppercase tracking-wider mb-1 truncate">
            {title}
          </p>
          <p className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white break-all">
            {value}
          </p>
          {subtitle && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 break-all">{subtitle}</p>
          )}
        </div>
        <div className={`p-2 rounded-xl bg-white/50 dark:bg-gray-800/50 ${iconColorClasses[color]} flex-shrink-0 ml-2`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

/**
 * Period selector for time series
 */
interface PeriodSelectorProps {
  days: number;
  granularity: 'day' | 'hour';
  onDaysChange: (days: number) => void;
  onGranularityChange: (g: 'day' | 'hour') => void;
}

function PeriodSelector({ days, granularity, onDaysChange, onGranularityChange }: PeriodSelectorProps) {
  const periodOptions = granularity === 'hour' ? [1, 3, 7] : [7, 14, 30];

  const formatLabel = (d: number) => {
    if (granularity === 'hour') {
      return `${d * 24}小时`;
    }
    return `${d}天`;
  };

  const handleGranularityChange = (g: 'day' | 'hour') => {
    onGranularityChange(g);
    const nextOptions = g === 'hour' ? [1, 3, 7] : [7, 14, 30];
    if (!nextOptions.includes(days)) {
      onDaysChange(nextOptions[0]);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {periodOptions.map((d) => (
          <button
            key={d}
            onClick={() => onDaysChange(d)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              days === d
                ? 'bg-orange-500 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            {formatLabel(d)}
          </button>
        ))}
      </div>
      <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        {(['day', 'hour'] as const).map((g) => (
          <button
            key={g}
            onClick={() => handleGranularityChange(g)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              granularity === g
                ? 'bg-orange-500 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            {g === 'day' ? '按天' : '按小时'}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Usage chart component
 */
interface UsageChartProps {
  data: TimeSeriesResponse | null;
  loading: boolean;
}

function UsageChart({ data, loading }: UsageChartProps) {
  if (loading) {
    return (
      <div className="h-full min-h-[300px] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!data || data.time_series.length === 0) {
    return (
      <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-gray-500">
        <BarChart3 className="w-8 h-8 mb-2 opacity-50" />
        <p>暂无使用数据</p>
      </div>
    );
  }

  // Transform data for chart
  const chartData = data.time_series.map((point) => ({
    period: new Date(point.period).toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      ...(data.granularity === 'hour' ? { hour: '2-digit' } : {}),
    }),
    calls: point.call_count,
    tokens: point.total_tokens,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={300}>
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" opacity={0.5} />
        <XAxis
          dataKey="period"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: '#e5e7eb' }}
        />
        <YAxis
          yAxisId="left"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(255,255,255,0.95)',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
          }}
        />
        <Legend verticalAlign="bottom" height={36} />
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="calls"
          name="调用次数"
          stroke="#f97316"
          strokeWidth={2}
          fill="url(#colorCalls)"
        />
        <Area
          yAxisId="right"
          type="monotone"
          dataKey="tokens"
          name="Tokens"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#colorTokens)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * Distribution pie chart component
 */
interface DistributionChartProps {
  data: Array<{ name: string; value: number }>;
  loading: boolean;
  activeIndex: number | null;
  onActiveChange: (index: number | null) => void;
}

function DistributionChart({ data, loading, activeIndex, onActiveChange }: DistributionChartProps) {
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[200px]">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-500 min-h-[200px]">
        <PieChartIcon className="w-8 h-8 mb-2 opacity-50" />
        <p>暂无分布数据</p>
      </div>
    );
  }

  const activeItem = activeIndex !== null ? data[activeIndex] : null;

  return (
    <div className="flex-1 relative min-h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={2}
            minAngle={2}
            dataKey="value"
            onMouseEnter={(_, index) => onActiveChange(index)}
            onMouseLeave={() => onActiveChange(null)}
          >
            {data.map((_entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={COLORS[index % COLORS.length]} 
                strokeWidth={activeIndex === index ? 2 : 0}
                stroke={activeIndex === index ? COLORS[index % COLORS.length] : undefined}
              />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      
      <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none z-10">
        <p className="text-xs text-gray-500 font-medium uppercase">Total</p>
        <p className="text-lg font-bold text-gray-900 dark:text-white">
          {(data.reduce((acc, curr) => acc + curr.value, 0) / 1000).toFixed(1)}k
        </p>
      </div>

      {activeItem && (
        <div className="absolute top-4 right-4 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-3 rounded-xl shadow-lg ring-1 ring-black/5 min-w-[150px]">
          <p className="font-semibold text-gray-900 dark:text-white text-sm mb-1">
            {activeItem.name}
          </p>
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <span 
              className="w-2 h-2 rounded-full" 
              style={{ backgroundColor: COLORS[activeIndex! % COLORS.length] }}
            />
            <span>{activeItem.value.toLocaleString()} Tokens</span>
          </div>
        </div>
      )}
    </div>
  );
}


/**
 * Main LLM Stats page component
 */
export default function LLMStatsPage() {

  const { token } = useAuth();

  // State
  const [summary, setSummary] = useState<LLMStatsSummary | null>(null);
  const [timeSeries, setTimeSeries] = useState<TimeSeriesResponse | null>(null);
  const [moduleDist, setModuleDist] = useState<ModuleDistributionResponse | null>(null);
  const [modelDist, setModelDist] = useState<ModelDistributionResponse | null>(null);
  const [toolDist, setToolDist] = useState<ToolDistributionResponse | null>(null);

  const [availableModules, setAvailableModules] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [tsLoading, setTsLoading] = useState(false);
  const [toolLoading, setToolLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

   // Filters
   const [days, setDays] = useState(7);
   const [granularity, setGranularity] = useState<'day' | 'hour'>('day');
   const [distTab, setDistTab] = useState<'module' | 'model'>('module');
   const [tableTab, setTableTab] = useState<'module' | 'model'>('module');

  const [customStart, setCustomStart] = useState<string>('');
  const [customEnd, setCustomEnd] = useState<string>('');

  // Tool filter states
  const [selectedModelForTool, setSelectedModelForTool] = useState<string>('');
  const [selectedModuleForTool, setSelectedModuleForTool] = useState<string>('');

  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Load initial data

  const loadData = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);

    try {
      const [summaryData, tsData, modDistData, modelDistData, modulesData, modelsData] = await Promise.all([
        getLLMStatsSummary(token),
        getLLMStatsTimeSeries(token, days, granularity),
        getLLMStatsDistributionByModule(token, customStart || undefined, customEnd || undefined),
        getLLMStatsDistributionByModel(token, customStart || undefined, customEnd || undefined),
        getLLMStatsModules(token),
        getLLMStatsModels(token),
      ]);

      setSummary(summaryData);
      setTimeSeries(tsData);
      setModuleDist(modDistData);
      setModelDist(modelDistData);
      setAvailableModules(modulesData.modules);
      setAvailableModels(modelsData.models);
    } catch (err) {
      console.error('Failed to load LLM stats:', err);
      setError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [token, days, granularity, customStart, customEnd]);

  // Load time series when filters change
  const loadTimeSeries = useCallback(async () => {
    if (!token) return;

    setTsLoading(true);
    try {
      const tsData = await getLLMStatsTimeSeries(token, days, granularity);
      setTimeSeries(tsData);
    } catch (err) {
      console.error('Failed to load time series:', err);
    } finally {
      setTsLoading(false);
    }
  }, [token, days, granularity]);

  // Load distribution when date range changes
  const loadDistribution = useCallback(async () => {
    if (!token) return;
    try {
      const [modDistData, modelDistData] = await Promise.all([
        getLLMStatsDistributionByModule(token, customStart || undefined, customEnd || undefined),
        getLLMStatsDistributionByModel(token, customStart || undefined, customEnd || undefined),
      ]);
      setModuleDist(modDistData);
      setModelDist(modelDistData);
    } catch (err) {
      console.error('Failed to reload distribution:', err);
    }
  }, [token, customStart, customEnd]);

  // Load tool statistics
  const loadToolStats = useCallback(async () => {
    if (!token) return;

    setToolLoading(true);
    try {
      const [toolDistData] = await Promise.all([
        getLLMStatsDistributionByTool(
          token,
          customStart || undefined,
          customEnd || undefined,
          selectedModelForTool || undefined,
          selectedModuleForTool || undefined
        ),
      ]);
      setToolDist(toolDistData);
    } catch (err) {
      console.error('Failed to load tool stats:', err);
    } finally {
      setToolLoading(false);
    }
  }, [token, days, granularity, customStart, customEnd, selectedModelForTool, selectedModuleForTool]);

  useEffect(() => {
    loadData();
  }, [loadData]); // Note: loadData depends on customStart/End now, so it will reload everything when they change.

  useEffect(() => {
    if (!loading) {
       loadTimeSeries();
    }
  }, [days, granularity]);
  
  useEffect(() => {
    if (!loading) {
      loadDistribution();
    }
  }, [customStart, customEnd]);

  useEffect(() => {
    loadToolStats();
  }, [loadToolStats]);


  // Process distribution data for charts
  const distChartData = distTab === 'module' 
    ? moduleDist?.distribution.map(d => ({ name: d.module_name, value: d.total_tokens })) || []
    : modelDist?.distribution.map(d => ({ name: d.model_name, value: d.total_tokens })) || [];

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-4">
        <Activity className="w-12 h-12 text-red-500 mb-4" />
        <p className="text-gray-600 dark:text-gray-300 mb-4">{error}</p>
        <button
          onClick={loadData}
          className="px-4 py-2 rounded-lg bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 transition-colors"
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-orange-500 font-semibold">
              Analytics
            </p>
            <h1 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <Activity className="w-5 h-5 md:w-6 md:h-6 text-orange-500" />
              LLM 使用统计
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              追踪 Token 消耗、模型调用和性能指标
            </p>
          </div>
          <button
            onClick={loadData}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 dark:hover:text-gray-300 transition-colors self-start md:self-auto"
            title="刷新数据"
          >
            <RefreshCcw className="w-4 h-4" />
          </button>
        </div>

        {/* Top Stats Row */}
        {/* <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4 mb-6"> */}
        <div className="grid grid-cols-2 lg:grid-cols-[3fr_2fr_2fr_2fr] gap-3 md:gap-4 mb-6">
          <StatCard
            title="总 Token 消耗"
            value={(summary?.total_tokens ?? 0).toLocaleString()}
            subtitle={`平均 ${summary?.avg_tokens_per_call.toFixed(0) ?? 0} / 次`}
            icon={<Layers className="w-5 h-5" />}
            color="blue"
          />
          <StatCard
            title="总调用次数"
            value={summary?.total_calls.toLocaleString() ?? 0}
            icon={<Zap className="w-5 h-5" />}
            color="orange"
          />
          <StatCard
            title="平均耗时"
            value={summary?.avg_duration_ms ? `${(summary.avg_duration_ms / 1000).toFixed(2)}s` : '-'}
            icon={<Clock className="w-5 h-5" />}
            color="violet"
          />
          <StatCard
            title="模型数量"
            value={modelDist?.count ?? 0}
            subtitle={undefined} 
            icon={<Cpu className="w-5 h-5" />}
            color="green"
          />
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Trends Chart */}
          <section className="lg:col-span-2 bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5 flex flex-col transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 md:w-9 md:h-9 rounded-xl bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 md:w-5 md:h-5 text-orange-500" />
                </div>
                <div>
                  <h2 className="font-semibold text-base md:text-lg">使用趋势</h2>
                  <p className="text-xs text-gray-500">
                    调用量与 Token 消耗
                  </p>
                </div>
              </div>
              <PeriodSelector
                days={days}
                granularity={granularity}
                onDaysChange={setDays}
                onGranularityChange={setGranularity}
              />
            </div>
            <div className="flex-1 min-h-0">
               <UsageChart data={timeSeries} loading={tsLoading} />
            </div>
          </section>

          {/* Distribution Chart */}
          <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5 flex flex-col h-full min-h-[400px] min-w-[320px] transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
            <div className="flex flex-col gap-4 h-full">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                   <div className="w-8 h-8 rounded-xl bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center shrink-0">
                     <PieChartIcon className="w-4 h-4 text-blue-500" />
                   </div>
                   <h2 className="font-semibold text-base md:text-lg whitespace-nowrap">Token 分布</h2>
                 </div>

                
                 <div className="flex bg-gray-100 dark:bg-gray-800 p-1 rounded-lg shrink-0">
                   <button
                     onClick={() => setDistTab('module')}
                     className={`px-3 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                       distTab === 'module'

                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                    }`}
                  >
                    按模块
                  </button>
                  <button
                    onClick={() => setDistTab('model')}
                     className={`px-3 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                       distTab === 'model'

                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                    }`}
                  >
                    按模型
                  </button>
                </div>
              </div>

              <div className="flex-1 flex flex-col justify-center">
                  <DistributionChart data={distChartData} loading={loading} activeIndex={activeIndex} onActiveChange={setActiveIndex} />
                  
                  <div className="mt-4 space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                     {distChartData.map((item, idx) => (
                       <div
                         key={idx}
                         className={`flex items-center justify-between text-xs rounded px-2 py-1 transition-colors cursor-pointer ${
                           activeIndex === idx 
                             ? 'bg-gray-100 dark:bg-gray-800' 
                             : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                         }`}
                         onMouseEnter={() => setActiveIndex(idx)}
                         onMouseLeave={() => setActiveIndex(null)}
                       >
                         <div className="flex items-center gap-2">
                           <div 
                             className="w-2 h-2 rounded-full" 
                             style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                           />
                           <span className="text-gray-600 dark:text-gray-300 truncate max-w-[120px]" title={item.name}>
                             {item.name}
                           </span>
                         </div>
                         <span className="font-mono text-gray-500">
                           {(item.value / 1000).toFixed(1)}k
                         </span>
                       </div>
                     ))}
                  </div>
               </div>

            </div>
          </section>
        </div>


        {/* Date Range Picker */}
        <div className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5 mb-6 flex items-center justify-between gap-4 flex-wrap transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
             <div className="flex items-center gap-2">
                 <div className="w-8 h-8 rounded-xl bg-violet-100 dark:bg-violet-500/10 flex items-center justify-center">
                    <Clock className="w-4 h-4 text-violet-500" />
                 </div>
                 <h2 className="font-semibold text-base md:text-lg">时间范围选择</h2>
             </div>
             <div className="flex items-center gap-3 flex-wrap">
                 <input 
                    type="datetime-local" 
                    className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-orange-500 focus:border-transparent outline-none"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                 />
                 <span className="text-gray-500">to</span>
                 <input 
                    type="datetime-local" 
                    className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-orange-500 focus:border-transparent outline-none"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                 />
                 {(customStart || customEnd) && (
                     <button 
                        onClick={() => { setCustomStart(''); setCustomEnd(''); }}
                        className="text-sm text-red-500 hover:text-red-600 px-2"
                     >
                        清除
                     </button>
                 )}
             </div>
        </div>

        {/* Detailed Table */}
        <div className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md">
           <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
             <h3 className="font-semibold text-gray-900 dark:text-white">{tableTab === 'module' ? '模块详情' : '模型详情'}</h3>
             <div className="flex bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
               <button
                 onClick={() => setTableTab('module')}
                 className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                   tableTab === 'module'
                     ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                     : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                 }`}
               >
                 模块详情
               </button>
               <button
                 onClick={() => setTableTab('model')}
                 className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                   tableTab === 'model'
                     ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                     : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                 }`}
               >
                 模型详情
               </button>
             </div>
           </div>
           <div className="overflow-x-auto">
             <table className="w-full text-sm text-left">
               <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 dark:text-gray-400">
                 <tr>
                   <th className="px-6 py-3 font-medium">{tableTab === 'module' ? '模块名称' : '模型名称'}</th>
                   <th className="px-6 py-3 font-medium text-right">调用次数</th>
                   <th className="px-6 py-3 font-medium text-right">总 Tokens</th>
                   <th className="px-6 py-3 font-medium text-right">平均 Tokens</th>
                   <th className="px-6 py-3 font-medium text-right">平均耗时</th>
                 </tr>
               </thead>
               <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {(tableTab === 'module' ? moduleDist?.distribution : modelDist?.distribution)?.map((item) => (
                    <tr key={tableTab === 'module' ? (item as ModuleDistribution).module_name : (item as ModelDistribution).model_name} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                      <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                        {tableTab === 'module' ? (item as ModuleDistribution).module_name : (item as ModelDistribution).model_name}
                      </td>
                      <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                        {item.call_count.toLocaleString()}
                      </td>

                     <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                       {item.total_tokens.toLocaleString()}
                     </td>
                     <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                       {Math.round(item.avg_tokens).toLocaleString()}
                     </td>
                     <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                       {Math.round(item.avg_duration_ms)}ms
                     </td>
                   </tr>
                 ))}
                 {((tableTab === 'module' && (!moduleDist || moduleDist.distribution.length === 0)) ||
                   (tableTab === 'model' && (!modelDist || modelDist.distribution.length === 0))) && (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                        暂无数据
                      </td>
                    </tr>
                 )}
               </tbody>
             </table>
           </div>
        </div>

        {/* Tool Statistics Section */}
        <div className="mt-6 bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-violet-100 dark:bg-violet-500/10 flex items-center justify-center">
                  <Cpu className="w-4 h-4 text-violet-500" />
                </div>
                <h3 className="font-semibold text-gray-900 dark:text-white">工具调用统计</h3>
              </div>
              <button
                onClick={loadToolStats}
                className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 dark:hover:text-gray-300 transition-colors"
                title="刷新工具数据"
              >
                <RefreshCcw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Tool Filters */}
          <div className="px-6 py-4 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-800">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
                  模型筛选:
                </label>
                <select
                  value={selectedModelForTool}
                  onChange={(e) => setSelectedModelForTool(e.target.value)}
                  className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
                >
                  <option value="">全部模型</option>
                  {availableModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
                  模块筛选:
                </label>
                <select
                  value={selectedModuleForTool}
                  onChange={(e) => setSelectedModuleForTool(e.target.value)}
                  className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
                >
                  <option value="">全部模块</option>
                  {availableModules.map((module) => (
                    <option key={module} value={module}>
                      {module}
                    </option>
                  ))}
                </select>
              </div>
              <PeriodSelector
                days={days}
                granularity={granularity}
                onDaysChange={setDays}
                onGranularityChange={setGranularity}
              />
            </div>
          </div>

          {/* Tool Distribution Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 dark:bg-gray-800/50 text-gray-500 dark:text-gray-400">
                <tr>
                  <th className="px-6 py-3 font-medium">工具名称</th>
                  <th className="px-6 py-3 font-medium text-right">调用次数</th>
                  <th className="px-6 py-3 font-medium text-right">输入 Token</th>
                  <th className="px-6 py-3 font-medium text-right">输出 Token</th>
                  {/* <th className="px-6 py-3 font-medium text-right">总 Token</th> */}
                  <th className="px-6 py-3 font-medium text-right">平均 Token</th>
                  <th className="px-6 py-3 font-medium text-right">平均耗时</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                {toolDist?.distribution.map((tool: ToolDistribution) => (
                  <tr key={tool.tool_name} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                    <td className="px-6 py-4">
                      <div className="relative group">
                        <div className="font-medium text-gray-900 dark:text-white max-w-[300px] truncate overflow-hidden whitespace-nowrap cursor-default">
                          {tool.tool_name}
                        </div>
                        {/* Tooltip */}
                        <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-50 pointer-events-none">
                          <div className="bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg py-2 px-3 whitespace-nowrap shadow-lg max-w-md break-all">
                            {tool.tool_name}
                          </div>
                          <div className="absolute left-4 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-700" />
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {tool.call_count.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {tool.input_tokens.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {tool.output_tokens.toLocaleString()}
                    </td>
                    {/* <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {tool.total_tokens.toLocaleString()}
                    </td> */}
                    <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {Math.round(tool.avg_tokens).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-600 dark:text-gray-300">
                      {Math.round(tool.avg_duration_ms)}ms
                    </td>
                  </tr>
                ))}
                {(!toolDist || toolDist.distribution.length === 0) && !toolLoading && (
                  <tr>
                    <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                      暂无工具调用数据
                    </td>
                  </tr>
                )}
                {toolLoading && (
                  <tr>
                    <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                      <Loader2 className="w-6 h-6 animate-spin mx-auto text-violet-500" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
