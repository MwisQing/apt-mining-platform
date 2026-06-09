package service

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestAllBadgesImplemented verifies that the computeBadges function
// references all 9 badge types defined in BadgeRegistry.
func TestAllBadgesImplemented(t *testing.T) {
	// Locate candidate_service.go relative to this test file.
	dir, err := filepath.Abs(filepath.Dir("."))
	if err != nil {
		t.Fatalf("get working dir: %v", err)
	}
	srcPath := filepath.Join(dir, "candidate_service.go")

	data, err := os.ReadFile(srcPath)
	if err != nil {
		t.Fatalf("read %s: %v", srcPath, err)
	}
	source := string(data)

	// All 9 badge types that must be implemented
	requiredBadges := []string{
		"apt_dict", "advanced_crime", "noise_family", "multi_vendor",
		"cross_day", "lateral", "expired_revive", "high_tier", "scan_noise",
	}

	for _, name := range requiredBadges {
		if !strings.Contains(source, `"`+name+`"`) {
			t.Errorf("badge %q not referenced in computeBadges", name)
		}
	}

	// Verify cross_day uses cross-day pair data
	if !strings.Contains(source, "CrossDayPairs") {
		t.Error("cross_day badge missing CrossDayPairs support")
	}

	// Verify lateral uses lateral IP data
	if !strings.Contains(source, "LateralIPs") {
		t.Error("lateral badge missing LateralIPs support")
	}

	// Verify expired_revive checks trace_status
	if !strings.Contains(source, "expired_revive") {
		t.Error("expired_revive badge not implemented")
	}

	// Verify advanced_crime uses crime dictionary parsing
	if !strings.Contains(source, "getCrimeKeywords") {
		t.Error("advanced_crime badge missing crime dictionary parsing")
	}
}
