package orb

import (
	"context"
	"fmt"
	"net/http"
)

// AuthOption is the interface for authentication strategies.
type AuthOption interface {
	authOption
}

// authOption is the unexported interface implemented by all auth strategies.
type authOption interface {
	wrap(next http.RoundTripper) http.RoundTripper
}

// WithNoAuth disables authentication (default).
func WithNoAuth() AuthOption {
	return noAuth{}
}

// WithBearerToken authenticates with a static Bearer token.
func WithBearerToken(token string) AuthOption {
	return WithBearerTokenFunc(func(_ context.Context) (string, error) {
		return token, nil
	})
}

// WithBearerTokenFunc authenticates with a dynamic Bearer token.
// The function is called on every request, enabling token refresh.
func WithBearerTokenFunc(fn func(ctx context.Context) (string, error)) AuthOption {
	return bearerAuth{tokenFn: fn}
}

// noAuth is a pass-through transport.
type noAuth struct{}

func (noAuth) wrap(next http.RoundTripper) http.RoundTripper { return next }

// bearerAuth adds Authorization: Bearer <token> to every request.
type bearerAuth struct {
	tokenFn func(ctx context.Context) (string, error)
}

func (a bearerAuth) wrap(next http.RoundTripper) http.RoundTripper {
	return &bearerTransport{tokenFn: a.tokenFn, next: next}
}

type bearerTransport struct {
	tokenFn func(ctx context.Context) (string, error)
	next    http.RoundTripper
}

func (t *bearerTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	req = req.Clone(req.Context())
	token, err := t.tokenFn(req.Context())
	if err != nil {
		return nil, fmt.Errorf("bearer: getting token: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	return t.next.RoundTrip(req)
}
