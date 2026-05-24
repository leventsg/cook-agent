/**
 * Chat Window Component
 * Main chat area with message display and empty state
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { BookOpen, Lightbulb, UtensilsCrossed } from 'lucide-react';
import type { Message } from '../../types';
import { MessageBubble } from './MessageBubble';

export interface ChatWindowProps {
    messages: Message[];
    isLoading: boolean;
    onSuggestionClick?: (text: string) => void;
    error?: string | null;
}

export function ChatWindow({ messages, isLoading, onSuggestionClick, error }: ChatWindowProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [isUserScrolling, setIsUserScrolling] = useState(false);

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
                <EmptyState onSuggestionClick={onSuggestionClick} />
            ) : (
                <div className="max-w-3xl mx-auto w-full">
                    {messages.map((message) => (
                        <MessageBubble key={message.id} message={message} hasError={!!error} />
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
 * Empty state with welcome message and suggestions
 */
function EmptyState({
    onSuggestionClick,
}: {
    onSuggestionClick?: (text: string) => void;
}) {
    return (
        <div className="flex flex-col items-center justify-center h-full w-full text-gray-500 dark:text-gray-400 animate-in fade-in duration-500 overflow-x-hidden px-4 box-border">
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

            {/* Feature Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 w-full max-w-3xl mb-6 sm:mb-8">
                <FeatureCard
                    icon={<BookOpen className="w-5 h-5" />}
                    title="Recipe Search"
                    description="Find detailed cooking instructions"
                />
                <FeatureCard
                    icon={<Lightbulb className="w-5 h-5" />}
                    title="Cooking Tips"
                    description="Learn professional techniques"
                />
                <FeatureCard
                    icon={<UtensilsCrossed className="w-5 h-5" />}
                    title="Ingredient Match"
                    description="Discover dishes you can make"
                />
            </div>

            {/* Suggestion Chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3 w-full max-w-2xl">
                <SuggestionChip
                    text="红烧肉怎么做？"
                    emoji="🥩"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="鸡蛋和西红柿能做什么？"
                    emoji="🥚"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="推荐一道健康晚餐"
                    emoji="🥗"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="如何让炒菜更香？"
                    emoji="✨"
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
    description,
}: {
    icon: React.ReactNode;
    title: string;
    description: string;
}) {
    return (
        <div className="p-5 bg-white dark:bg-gray-800 border border-gray-200/60 dark:border-gray-700/60 rounded-xl text-center shadow-sm hover:shadow-lg hover:shadow-orange-500/10 hover:-translate-y-1 transition-all duration-300">
            <div className="w-11 h-11 bg-gradient-to-br from-orange-100 to-orange-50 dark:from-orange-900/40 dark:to-orange-900/20 rounded-lg flex items-center justify-center mx-auto mb-3 text-orange-500 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300">
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
            className="flex items-center gap-3 px-4 py-3.5 bg-white dark:bg-gray-800 border border-gray-200/60 dark:border-gray-700/60 rounded-xl text-sm text-left hover:border-orange-400 dark:hover:border-orange-600 hover:shadow-lg hover:shadow-orange-500/10 hover:-translate-y-0.5 transition-all duration-300 text-gray-700 dark:text-gray-300 group"
            onClick={() => onClick?.(text)}
        >
            <span className="text-xl group-hover:scale-125 group-hover:rotate-3 transition-all duration-300">
                {emoji}
            </span>
            <span className="group-hover:text-orange-600 dark:group-hover:text-orange-400 transition-colors">{text}</span>
        </button>
    );
}

/**
 * Loading indicator when waiting for response
 */
function LoadingIndicator() {
    return (
        <div className="flex gap-4 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-400 to-orange-500 flex items-center justify-center shrink-0 shadow-sm">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="space-y-2 pt-2">
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <span className="animate-pulse">CookHero is thinking...</span>
                </div>
            </div>
        </div>
    );
}
