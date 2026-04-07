package orb

import (
	"context"
	"errors"
	"fmt"
)

var (
	ErrNotFound       = errors.New("orb: not found")
	ErrUnauthorized   = errors.New("orb: unauthorized")
	ErrForbidden      = errors.New("orb: forbidden")
	ErrConflict       = errors.New("orb: conflict")
	ErrORBUnavailable = errors.New("orb: service unavailable")
	ErrTimeout        = errors.New("orb: request timeout")
)

// APIError is returned for all HTTP error responses from ORB.
// Use errors.Is(err, orb.ErrNotFound) etc. for status-based checks.
// Use errors.As(err, &apiErr) to access StatusCode, Code, Message.
type APIError struct {
	StatusCode int
	Code       string
	Message    string
	Details    any
	sentinel   error
}

func (e *APIError) Error() string {
	if e.Code != "" {
		return fmt.Sprintf("orb: HTTP %d %s: %s", e.StatusCode, e.Code, e.Message)
	}
	return fmt.Sprintf("orb: HTTP %d: %s", e.StatusCode, e.Message)
}

func (e *APIError) Is(target error) bool {
	return e.sentinel != nil && errors.Is(e.sentinel, target)
}

func (e *APIError) Unwrap() error {
	return e.sentinel
}

// mapError converts network-level errors (context cancellation, dial failures)
// into typed APIError values. HTTP-level errors (4xx, 5xx) are handled by
// parseAPIError in client.go which reads the response body directly.
func mapError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return &APIError{StatusCode: 0, sentinel: ErrTimeout, Message: err.Error()}
	}
	// Network errors (dial failure, connection reset, etc.)
	// Wrap in APIError with ErrORBUnavailable sentinel
	var netErr interface{ Timeout() bool }
	if errors.As(err, &netErr) {
		return &APIError{StatusCode: 0, sentinel: ErrORBUnavailable, Message: err.Error()}
	}
	return err
}

func sentinelForStatus(code int) error {
	switch code {
	case 404:
		return ErrNotFound
	case 401:
		return ErrUnauthorized
	case 403:
		return ErrForbidden
	case 409:
		return ErrConflict
	case 503:
		return ErrORBUnavailable
	case 408:
		return ErrTimeout
	default:
		return nil
	}
}
