package repository

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestTracedPenaltyPresentInSource verifies that the candidate scoring SQL
// includes trace penalty deductions (-12 active, -4 expired) matching the
// 3.x Python scoring rules. This prevents silent regression.
func TestTracedPenaltyPresentInSource(t *testing.T) {
	// Locate candidate_repo.go relative to this test file.
	dir, err := filepath.Abs(filepath.Dir("."))
	if err != nil {
		t.Fatalf("get working dir: %v", err)
	}
	srcPath := filepath.Join(dir, "candidate_repo.go")

	data, err := os.ReadFile(srcPath)
	if err != nil {
		t.Fatalf("read %s: %v", srcPath, err)
	}
	source := string(data)

	tests := []struct {
		name    string
		fragment string
	}{
		{"active penalty -12", "tr.trace_status = 'active' THEN -12"},
		{"expired penalty -4", "tr.trace_status IS NOT NULL THEN -4"},
		{"TTL-based traced CTE", "make_interval(days =>"},
		{"active/expired in traced CTE", "THEN 'active' ELSE 'expired'"},
	}

	for _, tt := range tests {
		if !strings.Contains(source, tt.fragment) {
			t.Errorf("missing %q in candidate_repo.go", tt.name)
		}
	}
}
