// Package orb provides a Go client for the Open Resource Broker (ORB) API.
//
// Basic usage:
//
//	c, err := orb.NewClient(
//	    orb.WithBaseURL("http://localhost:8000"),
//	    orb.WithAuth(orb.WithNoAuth()),
//	)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer c.Close()
package orb
