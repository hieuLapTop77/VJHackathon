import { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function useApi(endpoint, options = {}) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fetch_ = useCallback(async (body) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}${endpoint}`, {
        method:  body ? "POST" : "GET",
        headers: { "Content-Type": "application/json" },
        body:    body ? JSON.stringify(body) : undefined,
        ...options,
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [endpoint]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetch_(); }, [fetch_]);
  return { data, loading, error, refetch: fetch_ };
}

export { API };
