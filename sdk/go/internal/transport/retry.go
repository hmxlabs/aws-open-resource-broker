package transport

import (
	"errors"
	"io"
	"net"
	"net/http"
	"time"
)

// RetryTransport retries idempotent requests on transient errors.
// It retries on: network errors, 429, 503.
// It never retries: non-idempotent methods (POST) on HTTP errors, 4xx (except 429).
type RetryTransport struct {
	Next       http.RoundTripper
	MaxRetries int
	BaseDelay  time.Duration
}

// NewRetryTransport wraps next with retry logic.
// maxRetries defaults to 3, baseDelay defaults to 500ms if zero.
func NewRetryTransport(next http.RoundTripper, maxRetries int, baseDelay time.Duration) *RetryTransport {
	if maxRetries <= 0 {
		maxRetries = 3
	}
	if baseDelay <= 0 {
		baseDelay = 500 * time.Millisecond
	}
	return &RetryTransport{Next: next, MaxRetries: maxRetries, BaseDelay: baseDelay}
}

func (t *RetryTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	var (
		resp *http.Response
		err  error
	)
	for attempt := 0; attempt <= t.MaxRetries; attempt++ {
		if attempt > 0 {
			delay := t.BaseDelay * (1 << (attempt - 1)) // exponential: 500ms, 1s, 2s
			select {
			case <-req.Context().Done():
				return nil, req.Context().Err()
			case <-time.After(delay):
			}
		}

		resp, err = t.Next.RoundTrip(req)
		if err != nil {
			// Network error — retry all methods
			if isRetryableNetworkError(err) {
				continue
			}
			return nil, err
		}

		// Success or non-retryable HTTP status
		if !shouldRetryStatus(req.Method, resp.StatusCode) {
			return resp, nil
		}

		// Drain and close body before retry
		resp.Body.Close()
	}
	return resp, err
}

func shouldRetryStatus(method string, status int) bool {
	switch status {
	case 429, 503:
		return true
	}
	// Only retry 5xx on idempotent methods
	if status >= 500 && method != http.MethodPost {
		return true
	}
	return false
}

func isRetryableNetworkError(err error) bool {
	// io.EOF is not retryable — it means the server closed the connection
	// and retrying would just get another EOF on the same dead connection.
	if errors.Is(err, io.EOF) {
		return false
	}
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}
	return false
}
