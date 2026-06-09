package handler

import "testing"

func TestMatchTagPreset(t *testing.T) {
	tests := []struct {
		filename    string
		wantName    string
		wantColor   string
	}{
		// Preset 1: 排查成功
		{"01排查成功.txt", "排查成功", "#67C23A"},
		{"01.排查成功.txt", "排查成功", "#67C23A"},
		{"查实成功.txt", "排查成功", "#67C23A"},
		// Preset 2: 重点设备
		{"02重点设备.txt", "重点设备", "#F56C6C"},
		{"02.重点设备.txt", "重点设备", "#F56C6C"},
		// Preset 3: 不好查
		{"03不好查.txt", "不好查", "#909399"},
		{"03.不好排查.txt", "不好查", "#909399"},
		// No preset match
		{"custom_tags.txt", "", ""},
		{"my_devices.txt", "", ""},
	}

	for _, tt := range tests {
		gotName, gotColor := matchTagPreset(tt.filename)
		if gotName != tt.wantName || gotColor != tt.wantColor {
			t.Errorf("matchTagPreset(%q) = (%q, %q), want (%q, %q)",
				tt.filename, gotName, gotColor, tt.wantName, tt.wantColor)
		}
	}
}
