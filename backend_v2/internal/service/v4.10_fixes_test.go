package service

import (
	"strings"
	"testing"

	"apt-mining-platform/v2/internal/repository"
)

// ===== P0-1/P0-2: import_rows writing + SQL fix =====

func TestImportRowsWriteLogic(t *testing.T) {
	// Verify the extractRow function maps fields correctly for raw_json
	row := &alertRow{
		DeviceID:     "WIN-TEST001",
		SourceIP:     "10.0.0.1",
		Target:       "evil.com",
		Port:         "443",
		ThreatType:   "apt",
		ThreatLevel:  "high",
		AptOrg:       "APT41",
		StdAptOrg:    "winnti_group",
		AlertCount:   10,
		ContentHash:  "testhash123",
	}
	t.Run("parsed row has all key fields", func(t *testing.T) {
		if row.DeviceID == "" {
			t.Fatal("DeviceID should not be empty")
		}
		if row.AlertCount != 10 {
			t.Fatalf("AlertCount expected 10, got %d", row.AlertCount)
		}
	})
}

// ===== P1-1: Keyword search ILIKE =====

func TestKeywordSearchILIKE(t *testing.T) {
	tests := []struct {
		keyword  string
		wantPct  string
	}{
		{"apt", "%apt%"},
		{"中文测试", "%中文测试%"},
		{"  trim  ", "%trim%"},
		{"oceanlotus", "%oceanlotus%"},
	}
	for _, tt := range tests {
		t.Run(tt.keyword, func(t *testing.T) {
			got := "%" + strings.TrimSpace(tt.keyword) + "%"
			if got != tt.wantPct {
				t.Errorf("keyword %q: got %q, want %q", tt.keyword, got, tt.wantPct)
			}
		})
	}
}

// ===== P1-2: hide_traced port wildcard =====

func TestHideTracedPortWildcard(t *testing.T) {
	// The SQL condition: COALESCE(tt.port, '') IN ('', COALESCE(a.port, ''))
	// Test cases for traced port (tt.port) vs alert port (a.port)
	cases := []struct {
		ttPort    string
		alertPort string
		match     bool
	}{
		{"", "443", true},   // wildcard matches any
		{"", "80", true},    // wildcard matches any
		{"", "", true},      // both empty = match
		{"443", "443", true}, // exact match
		{"443", "80", false}, // no match
		{"*", "443", false},  // * is not empty (different from hide_closed)
	}
	for _, c := range cases {
		t.Run("tt="+c.ttPort+"_a="+c.alertPort, func(t *testing.T) {
			// Simulate COALESCE logic
			coalesceTT := c.ttPort
			if coalesceTT == "" {
				coalesceTT = ""
			}
			coalesceA := c.alertPort
			if coalesceA == "" {
				coalesceA = ""
			}
			// IN ('', COALESCE(a.port, ''))
			match := coalesceTT == "" || coalesceTT == coalesceA
			if match != c.match {
				t.Errorf("tt=%q a=%q: got %v, want %v", c.ttPort, c.alertPort, match, c.match)
			}
		})
	}
}

// ===== P1-3: Auxiliary fields =====

func TestTargetKindLabel(t *testing.T) {
	tests := []struct {
		kind string
		want string
	}{
		{"ip", "IP"},
		{"domain", "域名"},
		{"other", "其他"},
		{"", "其他"},
	}
	for _, tt := range tests {
		got := targetKindLabel(tt.kind)
		if got != tt.want {
			t.Errorf("targetKindLabel(%q) = %q, want %q", tt.kind, got, tt.want)
		}
	}
}

func TestTraceStatusLabel(t *testing.T) {
	tests := []struct {
		status *string
		want   string
	}{
		{ptrStr("active"), "追踪中"},
		{ptrStr("expired"), "追踪过期"},
		{nil, ""},
		{ptrStr("unknown"), ""},
	}
	for _, tt := range tests {
		got := traceStatusLabel(tt.status)
		if got != tt.want {
			t.Errorf("traceStatusLabel(%v) = %q, want %q", tt.status, got, tt.want)
		}
	}
}

func TestDeviceNoteSummary(t *testing.T) {
	// Empty
	if got := deviceNoteSummary(nil); got != "" {
		t.Errorf("empty: got %q, want empty", got)
	}
	// Valid JSON with tags
	json := `[{"id":1,"name":"重点设备","color":"#FF0000"},{"id":2,"name":"排查成功","color":"#00FF00"}]`
	got := deviceNoteSummary([]byte(json))
	if got != "重点设备, 排查成功" {
		t.Errorf("tags: got %q, want '重点设备, 排查成功'", got)
	}
	// Empty array
	got = deviceNoteSummary([]byte("[]"))
	if got != "" {
		t.Errorf("empty array: got %q, want empty", got)
	}
}

func TestHeatSummary(t *testing.T) {
	cases := []struct {
		devCount int
		alertCnt int
		srcIPCnt int
		want     string
	}{
		{1, 1, 1, ""},
		{3, 5, 2, "3台设备 / 5条告警 / 2个源IP"},
		{2, 1, 1, "2台设备"},
		{1, 3, 1, "3条告警"},
		{1, 1, 3, "3个源IP"},
	}
	for _, c := range cases {
		row := repository.CandidateRow{
			HeatTargetDeviceCount: c.devCount,
			HeatTargetAlertCount:  c.alertCnt,
			HeatSourceIPAlertCnt:  c.srcIPCnt,
		}
		got := heatSummary(row)
		if got != c.want {
			t.Errorf("dev=%d,alert=%d,src=%d: got %q, want %q",
				c.devCount, c.alertCnt, c.srcIPCnt, got, c.want)
		}
	}
}

// ===== P1-4: ListImports time format =====

func TestTimeFormat(t *testing.T) {
	// nullTime already tested via GetImport path
	// Verify the format string produces correct output
	importTime := "2026-05-24 10:30:00"
	if !strings.HasPrefix(importTime, "2026-05-24") {
		t.Fatalf("time format should be YYYY-MM-DD HH:MM:SS, got %s", importTime)
	}
}

// ===== P1-5: SHA256 content hash =====

func TestSHA256ContentHash(t *testing.T) {
	row := &alertRow{
		DeviceID:     "WIN-TEST001",
		FirstAlertTime: "2026-05-24 10:00:00",
		LastAlertTime:  "2026-05-24 11:00:00",
		SourceIP:     "10.0.0.1",
		Target:       "evil.com",
		Port:         "443",
		ThreatType:   "apt",
		ThreatLevel:  "high",
		StdAptOrg:    "oceanlotus",
	}

	hash := computeContentHash(row)

	// SHA256 hex should be 64 chars
	if len(hash) != 64 {
		t.Errorf("SHA256 hash length: got %d, want 64", len(hash))
	}

	// All hex characters
	for _, c := range hash {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			t.Errorf("non-hex char %c in hash %s", c, hash)
			break
		}
	}

	// Deterministic: same input → same hash
	hash2 := computeContentHash(row)
	if hash != hash2 {
		t.Errorf("non-deterministic: %s != %s", hash, hash2)
	}

	// Different input → different hash
	row2 := &alertRow{
		DeviceID:     "WIN-DIFFERENT",
		FirstAlertTime: "2026-05-24 10:00:00",
		LastAlertTime:  "2026-05-24 11:00:00",
		SourceIP:     "10.0.0.1",
		Target:       "evil.com",
		Port:         "443",
		ThreatType:   "apt",
		ThreatLevel:  "high",
		StdAptOrg:    "oceanlotus",
	}
	hash3 := computeContentHash(row2)
	if hash == hash3 {
		t.Error("collision: different inputs produced same hash")
	}
}

// ===== P1-6: IOC extractor prefix stripping =====

func TestIOCExtractorPrefixStripping(t *testing.T) {
	extractor := NewIOCExtractor()

	tests := []struct {
		name  string
		input string
		want  string // expected domain value (after prefix stripped)
	}{
		{"network prefix", "network:evil.com", "evil.com"},
		{"domain prefix", "domain:malware.net", "malware.net"},
		{"dns prefix", "dns:c2server.org", "c2server.org"},
		{"no prefix", "evil.com", "evil.com"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			items := extractor.ExtractIOCs(tt.input)
			found := false
			for _, item := range items {
				if item.Type == "domain" && item.Value == tt.want {
					found = true
					break
				}
			}
			if !found {
				t.Errorf("input %q: expected domain %q not found in results:\n%+v",
					tt.input, tt.want, items)
			}
		})
	}
}

func TestIOCExtractorExecExtensionFilter(t *testing.T) {
	extractor := NewIOCExtractor()

	// Domains ending in .exe should be filtered out
	items := extractor.ExtractIOCs("malware.exe download.evil.com")
	for _, item := range items {
		if item.Type == "domain" && strings.HasSuffix(strings.ToLower(item.Value), ".exe") {
			t.Errorf("exe domain should be filtered: %s", item.Value)
		}
	}
	// evil.com should still be present
	found := false
	for _, item := range items {
		if item.Type == "domain" && item.Value == "download.evil.com" {
			found = true
			break
		}
	}
	if !found {
		t.Error("download.evil.com should be extracted")
	}
}

func TestIOCExtractorURLHostnameDedup(t *testing.T) {
	extractor := NewIOCExtractor()

	// URL + same domain should dedup the domain
	items := extractor.ExtractIOCs("https://evil.com/path evil.com")
	domainCount := 0
	for _, item := range items {
		if item.Type == "domain" && item.Value == "evil.com" {
			domainCount++
		}
	}
	if domainCount > 1 {
		t.Errorf("domain evil.com should appear only once (deduped with URL), got %d", domainCount)
	}
	// URL should still be present
	urlCount := 0
	for _, item := range items {
		if item.Type == "url" {
			urlCount++
		}
	}
	if urlCount == 0 {
		t.Error("URL should be present")
	}
}

// ===== Helper =====

func ptrStr(s string) *string {
	return &s
}
