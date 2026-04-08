package orb

import "time"

// Template represents an ORB resource template.
type Template struct {
	TemplateID  string
	Name        string
	Description string
	Provider    string
	Config      map[string]any
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// Machine represents a provisioned machine managed by ORB.
type Machine struct {
	MachineID  string
	Name       string
	Status     string
	PrivateIP  string
	PublicIP   string
	TemplateID string
	RequestID  string
	CreatedAt  time.Time
}

// Request represents an ORB machine provisioning request.
type Request struct {
	RequestID       string
	Status          string
	Message         string
	RequestedCount  int
	SuccessfulCount int
	FailedCount     int
	Machines        []MachineInfo
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

// MachineRequest is returned by RequestMachines.
type MachineRequest struct {
	RequestID string
	Message   string
}

// CreateTemplateRequest is the input for CreateTemplate.
type CreateTemplateRequest struct {
	Name        string
	Description string
	Provider    string
	Config      map[string]any
}

// UpdateTemplateRequest is the input for UpdateTemplate.
type UpdateTemplateRequest struct {
	Name        string
	Description string
	Config      map[string]any
}

// RequestMachinesRequest is the input for RequestMachines.
type RequestMachinesRequest struct {
	TemplateID string
	Count      int
	Metadata   map[string]any
}
