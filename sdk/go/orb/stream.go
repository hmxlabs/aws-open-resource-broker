package orb

import (
	"context"
	"sync/atomic"
)

// StreamEvent is a single status update from the ORB SSE stream.
type StreamEvent struct {
	RequestID       string
	Status          string
	Message         string
	RequestedCount  int
	SuccessfulCount int
	FailedCount     int
	Machines        []MachineInfo
}

// MachineInfo holds per-machine status within a StreamEvent.
type MachineInfo struct {
	MachineID  string
	Name       string
	Status     string
	Result     string
	PrivateIP  string
	PublicIP   string
	LaunchTime string
	Message    string
}

// RequestStream is a live SSE stream for a single ORB request.
// Call Next() in a loop; call Close() when done or on error.
type RequestStream struct {
	ch     chan StreamEvent
	cancel context.CancelFunc
	errPtr atomic.Pointer[error]
	done   chan struct{}
}

// Next returns the next event. ok is false when the stream is closed.
func (s *RequestStream) Next() (StreamEvent, bool) {
	ev, ok := <-s.ch
	return ev, ok
}

// Err returns any error that caused the stream to close abnormally.
func (s *RequestStream) Err() error {
	if p := s.errPtr.Load(); p != nil {
		return *p
	}
	return nil
}

// Close stops the stream and waits for the producer goroutine to exit.
// Safe to call multiple times.
func (s *RequestStream) Close() {
	s.cancel()
	for range s.ch {
	}
	<-s.done
}
