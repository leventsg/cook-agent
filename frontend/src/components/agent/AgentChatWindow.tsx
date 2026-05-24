/**
 * Agent Chat Window Component
 * Main chat area with message display and empty state for Agent mode
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { Bot, Calculator, Code } from 'lucide-react';
import type { Message } from '../../types';
import { AgentMessageBubble } from './AgentMessageBubble';

export interface AgentChatWindowProps {
    messages: Message[];
    isLoading: boolean;
    onSuggestionClick?: (text: string) => void;
    error?: string | null;
    isToolSelectorOpen?: boolean;
}

export function AgentChatWindow({ messages, isLoading, onSuggestionClick, error, isToolSelectorOpen }: AgentChatWindowProps) {
    messages = messages.filter(
        (message) =>
        (message.role === 'user' || message.role === 'assistant') && 
        ((message.content !== null && message.content !== undefined && message.content !== '') || message.trace !== undefined)
    )
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [isUserScrolling, setIsUserScrolling] = useState(false);
    const prevMessagesLengthRef = useRef(messages.length);

    // Check if user is near the bottom of the scroll container
    const checkIsNearBottom = useCallback(() => {
        const container = scrollContainerRef.current;
        if (!container) return true;

        const { scrollTop, scrollHeight, clientHeight } = container;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        return distanceFromBottom < 100;
    }, []);

    // Handle scroll events to track user interaction
    const handleScroll = useCallback(() => {
        if (!isUserScrolling) {
            setIsUserScrolling(true);
            // Reset user scrolling flag after a short delay
            setTimeout(() => setIsUserScrolling(false), 1000);
        }
        setIsNearBottom(checkIsNearBottom());
    }, [isUserScrolling, checkIsNearBottom]);

    // Force scroll to bottom when user sends a new message
    useEffect(() => {
        const prevLength = prevMessagesLengthRef.current;
        const currentLength = messages.length;

        // Check if a new user message was added
        if (currentLength > prevLength && messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            // If the new message is from user, force scroll to bottom
            if (lastMessage.role === 'user') {
                messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }
        }

        prevMessagesLengthRef.current = currentLength;
    }, [messages]);

    // Auto-scroll to bottom when new messages arrive, but only if user is near bottom
    useEffect(() => {
        if (isNearBottom && !isUserScrolling && messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isNearBottom, isUserScrolling]);

    // Set up scroll event listener
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            container.addEventListener('scroll', handleScroll, { passive: true });
            return () => container.removeEventListener('scroll', handleScroll);
        }
    }, [handleScroll]);

    // Initialize near bottom state
    useEffect(() => {
        setIsNearBottom(checkIsNearBottom());
    }, [checkIsNearBottom]);

    const isEmpty = messages.length === 0;

    return (
        <div
            ref={scrollContainerRef}
            className={`
        flex-1 p-4 md:p-6
        bg-gradient-to-b from-white to-gray-50 dark:from-gray-900 dark:to-gray-950
        ${isEmpty ? 'overflow-y-hidden' : 'overflow-y-auto'}
      `}
        >
            {isEmpty ? (
                <EmptyState onSuggestionClick={onSuggestionClick} isToolSelectorOpen={isToolSelectorOpen} />
            ) : (
                <div className="max-w-3xl mx-auto w-full">
                    {messages
                    .map((message) => (
                        <AgentMessageBubble key={message.id} message={message} hasError={!!error} />
                    ))}

                    {/* Loading indicator */}
                    {isLoading &&
                        messages.length > 0 &&
                        messages[messages.length - 1].role === 'user' && (
                            <LoadingIndicator />
                        )}
                </div>
            )}
            {!isEmpty && <div ref={messagesEndRef} className="h-4" />}
        </div>
    );
}

/**
 * Empty state with welcome message and suggestions for Agent mode
 */
function EmptyState({
    onSuggestionClick,
    isToolSelectorOpen
}: {
    onSuggestionClick?: (text: string) => void;
    isToolSelectorOpen?: boolean;
}) {
    return (
        <div className="flex flex-col items-center justify-center h-full w-full text-gray-500 dark:text-gray-400 animate-in fade-in duration-500 overflow-x-hidden px-4 box-border">
            {/* <section className="relative flex-1 flex flex-col items-center justify-center overflow-hidden">
                <div className="flex items-center gap-4">
                    <div className="w-20 h-20 bg-orange-100 dark:bg-orange-900/30 rounded-2xl flex items-center justify-center text-orange-600 dark:text-orange-400 shrink-0 overflow-hidden">
                        <img src="/image.png" alt="CookHero Logo" className="w-full h-full object-contain p-2" />
                    </div>
                    <div className="w-100 h-48 max-w-5xl mx-auto flex items-center justify-center">
                        <img
                            src="/image.png"
                            alt="CookHero Logo"
                            className="w-full max-w-4xl object-contain transition-all duration-500 group-hover:scale-105"
                        />
                    </div>
                    <div>
                        <h2 className="text-3xl font-bold text-orange-600 dark:text-orange-400">
                            Your Personal Agent
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mt-1">
                            Calculate, analyze, and plan with intelligent tools
                        </p>
                    </div>
                </div>
            </section> */}
            {!isToolSelectorOpen && (
                <section className="empty-state-hero relative flex-1 flex flex-col items-center justify-center overflow-hidden">
                    <div className="relative group w-full px-4">
                        <div className="w-100 h-48 max-w-5xl mx-auto flex items-center justify-center">
                            <img
                                src="/image.png"
                                alt="CookHero Logo"
                                className="w-full max-w-4xl object-contain transition-all duration-500 group-hover:scale-105"
                            />
                        </div>
                    </div>
                </section>
            )}

            {/* Agent Feature Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 w-full max-w-3xl mb-6 sm:mb-8">
                <FeatureCard
                    icon={<Calculator className="w-5 h-5" />}
                    title="Calculation"
                    description="Unit conversions & scaling"
                />
                <FeatureCard
                    icon={<Code className="w-5 h-5" />}
                    title="Data Analysis"
                    description="Analyze nutritional data"
                />
                <FeatureCard
                    icon={<Bot className="w-5 h-5" />}
                    title="Complex Planning"
                    description="Meal prep & shopping lists"
                />
            </div>

            {/* Suggestion Chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3 w-full max-w-2xl">
                <SuggestionChip
                    text="计算 20 克鸡肉的卡路里"
                    emoji="🐔"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="帮我记录一下今天的午餐"
                    emoji="⚖️"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="为 2 人制定一周备餐计划"
                    emoji="📅"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="分析豆腐和牛肉的蛋白质含量"
                    emoji="📊"
                    onClick={onSuggestionClick}
                />
            </div>
        </div>
    );
}

/**
 * Feature card in empty state
 */
function FeatureCard({
    icon,
    title,
    description
}: {
    icon: React.ReactNode;
    title: string;
    description: string;
}) {
    return (
        <div className="p-5 bg-white dark:bg-gray-800 border border-gray-200/60 dark:border-gray-700/60 rounded-xl text-center shadow-sm hover:shadow-lg hover:shadow-indigo-500/10 hover:-translate-y-1 transition-all duration-300">
            <div className="w-11 h-11 rounded-lg flex items-center justify-center mx-auto mb-3 bg-gradient-to-br from-indigo-100 to-indigo-50 dark:from-indigo-900/40 dark:to-indigo-900/20 text-indigo-600 dark:text-indigo-400 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300">
                {icon}
            </div>
            <h3 className="font-semibold text-gray-800 dark:text-gray-100 mb-1.5">
                {title}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
        </div>
    );
}

/**
 * Suggestion chip button
 */
function SuggestionChip({
    text,
    emoji,
    onClick,
}: {
    text: string;
    emoji: string;
    onClick?: (text: string) => void;
}) {
    return (
        <button
            className="flex items-center gap-3 px-4 py-3.5 bg-white dark:bg-gray-800 border border-gray-200/60 dark:border-gray-700/60 rounded-xl text-sm text-left hover:border-indigo-400 dark:hover:border-indigo-600 hover:shadow-lg hover:shadow-indigo-500/10 hover:-translate-y-0.5 transition-all duration-300 text-gray-700 dark:text-gray-300 group"
            onClick={() => onClick?.(text)}
        >
            <span className="text-xl group-hover:scale-125 group-hover:rotate-3 transition-all duration-300">
                {emoji}
            </span>
            <span className="group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{text}</span>
        </button>
    );
}

/**
 * Loading indicator when waiting for response
 */
function LoadingIndicator() {
    return (
        <div className="flex gap-4 mb-6">
            <div className="w-10 h-10 rounded-xl bg-orange-500 flex items-center justify-center shrink-0 shadow-sm">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="space-y-2 pt-2">
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <span className="animate-pulse">Agent is thinking...</span>
                </div>
            </div>
        </div>
    );
}
