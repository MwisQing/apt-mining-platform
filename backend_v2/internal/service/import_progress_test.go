package service

import "testing"

func TestImportFinalStatus(t *testing.T) {
	tests := []struct {
		name     string
		progress importProgress
		want     string
	}{
		{
			name:     "all rows inserted or skipped is success",
			progress: importProgress{inserted: 10, skipped: 3},
			want:     "success",
		},
		{
			name:     "mixed good rows and issues is partial",
			progress: importProgress{inserted: 10, failed: 1},
			want:     "partial",
		},
		{
			name:     "missing required fields with good rows is partial",
			progress: importProgress{inserted: 10, raw: 2},
			want:     "partial",
		},
		{
			name:     "only issue rows is failed",
			progress: importProgress{failed: 2, raw: 1},
			want:     "failed",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := finalImportStatus(tt.progress); got != tt.want {
				t.Fatalf("finalImportStatus() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestImportProcessedRows(t *testing.T) {
	progress := importProgress{inserted: 5, skipped: 4, failed: 3, raw: 2}
	if got := progress.processedRows(); got != 14 {
		t.Fatalf("processedRows() = %d, want 14", got)
	}
}
