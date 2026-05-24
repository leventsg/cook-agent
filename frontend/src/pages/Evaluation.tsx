/**
 * RAG Evaluation Dashboard Page
 * Displays evaluation statistics, trends, and quality alerts
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCcw,
  Target,
  TrendingUp,
  XCircle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Zap,
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
  RadialBarChart,
  RadialBar,
} from 'recharts';
import { useAuth } from '../contexts';
import {
  getEvaluationStatistics,
  getEvaluationTrends,
  getEvaluationAlerts,
  getEvaluationHealth,
} from '../services/api/evaluation';
import type {
  EvaluationStatistics,
  TrendsResponse,
  AlertsResponse,
  EvaluationHealth,
  EvaluationAlert,
} from '../types/evaluation';

// Metric display names
const METRIC_LABELS: Record<string, string> = {
  faithfulness: '忠实度',
  answer_relevancy: '答案相关性',
};

// Chart colors
const CHART_COLORS = {
  faithfulness: '#f97316', // orange-500
  answer_relevancy: '#3b82f6', // blue-500
};

/**
 * Circular progress gauge for metrics
 */
interface MetricGaugeProps {
  label: string;
  value: number | null;
  min?: number | null;
  max?: number | null;
  color: string;
  threshold?: number;
}

function MetricGauge({ label, value, min, max, color, threshold = 0.5 }: MetricGaugeProps) {
  const displayValue = value !== null && !isNaN(value) ? Math.round(value * 100) : 0;
  const isLow = value !== null && !isNaN(value) && value < threshold;

  const data = [
    {
      name: label,
      value: displayValue,
      fill: color,
    },
  ];

  return (
    <div className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl p-4 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
        {isLow && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400">
            低于阈值
          </span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <div className="w-24 h-24">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              cx="50%"
              cy="50%"
              innerRadius="70%"
              outerRadius="100%"
              startAngle={90}
              endAngle={-270}
              data={data}
            >
              <RadialBar
                background={{ fill: '#e5e7eb' }}
                dataKey="value"
                cornerRadius={10}
              />
            </RadialBarChart>
          </ResponsiveContainer>
          <div className="relative -mt-16 text-center">
            <span className="text-2xl font-bold" style={{ color }}>
              {value !== null && !isNaN(value) ? `${displayValue}%` : '-'}
            </span>
          </div>
        </div>
        <div className="flex-1 space-y-1 text-xs text-gray-500">
          {min !== null && min !== undefined && !isNaN(min) && (
            <div className="flex justify-between">
              <span>最低</span>
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {Math.round(min * 100)}%
              </span>
            </div>
          )}
          {max !== null && max !== undefined && !isNaN(max) && (
            <div className="flex justify-between">
              <span>最高</span>
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {Math.round(max * 100)}%
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Stat card component
 */
interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color?: 'orange' | 'blue' | 'green' | 'red' | 'gray';
}

function StatCard({ title, value, subtitle, icon, color = 'orange' }: StatCardProps) {
  const colorClasses = {
    orange: 'from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 border-orange-200 dark:border-orange-800',
    blue: 'from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border-blue-200 dark:border-blue-800',
    green: 'from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 border-emerald-200 dark:border-emerald-800',
    red: 'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-800',
    gray: 'from-gray-50 to-gray-100 dark:from-gray-900/20 dark:to-gray-800/20 border-gray-200 dark:border-gray-800',
  };

  const iconColorClasses = {
    orange: 'text-orange-500',
    blue: 'text-blue-500',
    green: 'text-emerald-500',
    red: 'text-red-500',
    gray: 'text-gray-500',
  };

  return (
    <div className={`bg-gradient-to-br ${colorClasses[color]} border rounded-2xl p-4 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 font-medium uppercase tracking-wider mb-1">
            {title}
          </p>
          <p className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white">
            {value}
          </p>
          {subtitle && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
          )}
        </div>
        <div className={`p-2 rounded-xl bg-white/50 dark:bg-gray-800/50 ${iconColorClasses[color]}`}>
          {icon}
        </div>
      </div>
    </div>
  );
}

/**
 * Period selector for trends
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
 * Trend chart component
 */
interface TrendChartProps {
  data: TrendsResponse | null;
  loading: boolean;
}

function TrendChart({ data, loading }: TrendChartProps) {
  if (loading) {
    return (
      <div className="h-full min-h-[300px] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!data || data.trends.length === 0) {
    return (
      <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-gray-500">
        <BarChart3 className="w-8 h-8 mb-2 opacity-50" />
        <p>暂无趋势数据</p>
      </div>
    );
  }

  // Transform data for chart
  const chartData = data.trends.map((point) => ({
    period: new Date(point.period).toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      ...(data.granularity === 'hour' ? { hour: '2-digit' } : {}),
    }),
    count: point.count,
    faithfulness: point.metrics.faithfulness !== null && !isNaN(point.metrics.faithfulness) ? +(point.metrics.faithfulness * 100).toFixed(1) : null,
    answer_relevancy: point.metrics.answer_relevancy !== null && !isNaN(point.metrics.answer_relevancy) ? +(point.metrics.answer_relevancy * 100).toFixed(1) : null,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={300}>
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="colorFaithfulness" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={CHART_COLORS.faithfulness} stopOpacity={0.3} />
            <stop offset="95%" stopColor={CHART_COLORS.faithfulness} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorRelevancy" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={CHART_COLORS.answer_relevancy} stopOpacity={0.3} />
            <stop offset="95%" stopColor={CHART_COLORS.answer_relevancy} stopOpacity={0} />
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
          domain={[0, 100]}
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(255,255,255,0.95)',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
          }}
          formatter={(value) => [`${value}%`, '']}
        />
        <Legend
          verticalAlign="bottom"
          height={36}
          formatter={(value) => METRIC_LABELS[value] || value}
        />
        <Area
          type="monotone"
          dataKey="faithfulness"
          stroke={CHART_COLORS.faithfulness}
          strokeWidth={2}
          fill="url(#colorFaithfulness)"
          name="faithfulness"
          connectNulls
        />
        <Area
          type="monotone"
          dataKey="answer_relevancy"
          stroke={CHART_COLORS.answer_relevancy}
          strokeWidth={2}
          fill="url(#colorRelevancy)"
          name="answer_relevancy"
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * Alert item component
 */
interface AlertItemProps {
  alert: EvaluationAlert;
}

function AlertItem({ alert }: AlertItemProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-red-200 dark:border-red-800/50 rounded-xl overflow-hidden bg-gradient-to-r from-red-50 to-white dark:from-red-900/10 dark:to-gray-900">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-3 md:p-4 flex items-start gap-3 text-left hover:bg-red-50/50 dark:hover:bg-red-900/20 transition-colors"
      >
        <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {alert.violated_thresholds.map((threshold) => (
              <span
                key={threshold}
                className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300"
              >
                {METRIC_LABELS[threshold] || threshold}
              </span>
            ))}
          </div>
          <p className="text-sm text-gray-900 dark:text-gray-100 line-clamp-1 mb-2">
            {alert.query}
          </p>
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1 text-xs text-gray-500">
              <div className="flex items-center gap-1">
                <Target className="w-3 h-3" />
                忠实度: {alert.faithfulness !== null && !isNaN(alert.faithfulness) ? `${(alert.faithfulness * 100).toFixed(0)}%` : '-'}
              </div>
              <div className="flex items-center gap-1">
                <Activity className="w-3 h-3" />
                相关性: {alert.answer_relevancy !== null && !isNaN(alert.answer_relevancy) ? `${(alert.answer_relevancy * 100).toFixed(0)}%` : '-'}
              </div>
            </div>
            <div className="flex items-center text-xs text-gray-500 ml-4">
              {new Date(alert.created_at).toLocaleDateString('zh-CN')}
            </div>
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-red-200/50 dark:border-red-800/30 pt-3 space-y-3">
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">用户查询</p>
            <p className="text-sm text-gray-800 dark:text-gray-200 bg-white dark:bg-gray-800 rounded-lg p-3">
              {alert.query}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">AI 回复</p>
            <p className="text-sm text-gray-800 dark:text-gray-200 bg-white dark:bg-gray-800 rounded-lg p-3 max-h-32 overflow-y-auto">
              {alert.response}
            </p>
          </div>
          <div className="flex items-center gap-2 pt-2">
            <a
              href={`/chat/${alert.conversation_id}`}
              className="inline-flex items-center gap-1 text-xs text-orange-600 hover:text-orange-700 dark:text-orange-400"
            >
              <ExternalLink className="w-3 h-3" />
              查看对话
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Alert list component
 */
interface AlertListProps {
  data: AlertsResponse | null;
  loading: boolean;
}

function AlertList({ data, loading }: AlertListProps) {
  if (loading) {
    return (
      <div className="h-48 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!data || data.alerts.length === 0) {
    return (
      <div className="h-48 flex flex-col items-center justify-center text-gray-500">
        <CheckCircle2 className="w-8 h-8 mb-2 text-green-500 opacity-50" />
        <p>暂无质量警报</p>
        <p className="text-xs mt-1">所有评估指标均在阈值之上</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
      {data.alerts.map((alert) => (
        <AlertItem key={alert.id} alert={alert} />
      ))}
    </div>
  );
}

/**
 * Health status badge
 */
function HealthBadge({ health }: { health: EvaluationHealth | null }) {
  if (!health) return null;

  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full ${
          health.enabled
            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
        }`}
      >
        {health.enabled ? (
          <>
            <CheckCircle2 className="w-3 h-3" />
            评估已启用
          </>
        ) : (
          <>
            <XCircle className="w-3 h-3" />
            评估已禁用
          </>
        )}
      </span>
      {health.enabled && (
        <span className="text-gray-500">
          采样率: {(health.sample_rate * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

/**
 * Main evaluation page component
 */
export default function EvaluationPage() {
  const { token } = useAuth();

  // State
  const [stats, setStats] = useState<EvaluationStatistics | null>(null);
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [health, setHealth] = useState<EvaluationHealth | null>(null);

  const [loading, setLoading] = useState(true);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Trend filters
  const [days, setDays] = useState(7);
  const [granularity, setGranularity] = useState<'day' | 'hour'>('day');

  // Load initial data
  const loadData = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);

    try {
      const [statsData, trendsData, alertsData, healthData] = await Promise.all([
        getEvaluationStatistics(token),
        getEvaluationTrends(token, days, granularity),
        getEvaluationAlerts(token, 20),
        getEvaluationHealth(token),
      ]);

      setStats(statsData);
      setTrends(trendsData);
      setAlerts(alertsData);
      setHealth(healthData);
    } catch (err) {
      console.error('Failed to load evaluation data:', err);
      setError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [token, days, granularity]);

  // Load trends when filters change
  const loadTrends = useCallback(async () => {
    if (!token) return;

    setTrendsLoading(true);
    try {
      const trendsData = await getEvaluationTrends(token, days, granularity);
      setTrends(trendsData);
    } catch (err) {
      console.error('Failed to load trends:', err);
    } finally {
      setTrendsLoading(false);
    }
  }, [token, days, granularity]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!loading) {
      loadTrends();
    }
  }, [days, granularity]);

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
        <AlertTriangle className="w-12 h-12 text-red-500 mb-4" />
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
              <BarChart3 className="w-5 h-5 md:w-6 md:h-6 text-orange-500" />
              RAG 评估监控
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              查看检索增强生成的质量指标和趋势
            </p>
          </div>
          <div className="flex items-center gap-3">
            <HealthBadge health={health} />
            <button
              onClick={loadData}
              className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 dark:hover:text-gray-300 transition-colors"
              title="刷新数据"
            >
              <RefreshCcw className="w-4 h-4" />
            </button>
          </div>
        </div>


        {/* Top Stats Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4 mb-6">
          <StatCard
            title="总评估数"
            value={stats?.total_evaluations ?? 0}
            subtitle={`待处理: ${stats?.pending_count ?? 0}`}
            icon={<Activity className="w-5 h-5" />}
            color="orange"
          />
          <StatCard
            title="质量警报"
            value={alerts?.count ?? 0}
            subtitle="低于阈值的评估"
            icon={<AlertTriangle className="w-5 h-5" />}
            color={alerts && alerts.count > 0 ? 'red' : 'green'}
          />
          <StatCard
            title="平均耗时"
            value={stats?.avg_evaluation_duration_ms ? `${(stats.avg_evaluation_duration_ms / 1000).toFixed(1)}s` : '-'}
            subtitle="每次评估"
            icon={<Clock className="w-5 h-5" />}
            color="blue"
          />
          <StatCard
            title="失败评估"
            value={stats?.failed_count ?? 0}
            subtitle="需要关注"
            icon={<Zap className="w-5 h-5" />}
            color={stats && stats.failed_count > 0 ? 'red' : 'gray'}
          />
        </div>

        {/* Metric Gauges */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <MetricGauge
            label="忠实度 (Faithfulness)"
            value={stats?.metrics.faithfulness.mean ?? null}
            min={stats?.metrics.faithfulness.min}
            max={stats?.metrics.faithfulness.max}
            color={CHART_COLORS.faithfulness}
            threshold={health?.alert_thresholds?.faithfulness ?? 0.5}
          />
          <MetricGauge
            label="答案相关性 (Answer Relevancy)"
            value={stats?.metrics.answer_relevancy.mean ?? null}
            min={stats?.metrics.answer_relevancy.min}
            max={stats?.metrics.answer_relevancy.max}
            color={CHART_COLORS.answer_relevancy}
            threshold={health?.alert_thresholds?.answer_relevancy ?? 0.5}
          />
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Trends Chart */}
          <section className="lg:col-span-2 bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5 flex flex-col transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 md:w-9 md:h-9 rounded-xl bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 md:w-5 md:h-5 text-orange-500" />
                </div>
                <div>
                  <h2 className="font-semibold text-base md:text-lg">指标趋势</h2>
                  <p className="text-xs text-gray-500">
                    {trends?.data_points ?? 0} 个数据点
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
               <TrendChart data={trends} loading={trendsLoading} />
            </div>
          </section>

          {/* Alerts List */}
          <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5 flex flex-col h-full min-h-[400px] transition-all duration-200 hover:shadow-md hover:-translate-y-0.5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 md:w-9 md:h-9 rounded-xl bg-red-100 dark:bg-red-500/10 flex items-center justify-center">
                <AlertTriangle className="w-4 h-4 md:w-5 md:h-5 text-red-500" />
              </div>
              <div>
                <h2 className="font-semibold text-base md:text-lg">质量警报</h2>
                <p className="text-xs text-gray-500">
                  阈值: 忠实度 {((health?.alert_thresholds?.faithfulness ?? 0.5) * 100).toFixed(0)}%,
                  相关性 {((health?.alert_thresholds?.answer_relevancy ?? 0.5) * 100).toFixed(0)}%
                </p>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto pr-1 custom-scrollbar">
               <AlertList data={alerts} loading={loading} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
