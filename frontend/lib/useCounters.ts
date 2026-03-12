import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from './apiClient';

export interface Counters {
  added_today: number;
  due_soon: number;
  ignored: number;
  generated_at?: string;
}

export function useCounters() {
  const [counters, setCounters] = useState<Counters | null>(null);
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchCounters = useCallback(async () => {
    // Abort previous request if active
    if (abortControllerRef.current) {
        abortControllerRef.current.abort();
    }
    
    const controller = new AbortController();
    abortControllerRef.current = controller;
    
    setLoading(true);
    try {
      const res = await apiFetch('/api/licitacoes/counters', {
        signal: controller.signal
      });
      if (!res.ok) throw new Error('Failed to fetch counters');
      const data = await res.json();
      setCounters(data);
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error('Error fetching counters:', error);
      }
    } finally {
        if (abortControllerRef.current === controller) {
            setLoading(false);
        }
    }
  }, []);

  // Polling & Visibility Logic
  useEffect(() => {
    fetchCounters(); // Initial fetch

    const intervalId = setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchCounters();
      }
    }, 30000); // Poll every 30s

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchCounters();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (abortControllerRef.current) {
          abortControllerRef.current.abort();
      }
    };
  }, [fetchCounters]);

  return { 
    counters, 
    loading, 
    refreshCounters: fetchCounters 
  };
}
