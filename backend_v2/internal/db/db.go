package db

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"

	_ "github.com/lib/pq"
)

var (
	globalDB *sql.DB
)

// Connect 连接 PostgreSQL，返回新的连接
func Connect() (*sql.DB, error) {
	dbName := os.Getenv("APT_DB_NAME")
	if dbName == "" {
		dbName = "apt_mining_prod"
	}

	dbHost := os.Getenv("APT_DB_HOST")
	if dbHost == "" {
		dbHost = "127.0.0.1"
	}

	dbPort := os.Getenv("APT_DB_PORT")
	if dbPort == "" {
		dbPort = "5432"
	}

	dbUser := os.Getenv("APT_DB_USER")
	if dbUser == "" {
		dbUser = "postgres"
	}

	dbPass := os.Getenv("APT_DB_PASSWORD")

	connStr := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		dbHost, dbPort, dbUser, dbPass, dbName,
	)

	conn, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	conn.SetMaxOpenConns(20)
	conn.SetMaxIdleConns(5)
	conn.SetConnMaxLifetime(30 * time.Minute)

	if err := conn.Ping(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return conn, nil
}

// SetGlobalDB 设置全局数据库连接（main.go 中调用）
func SetGlobalDB(db *sql.DB) {
	globalDB = db
}

// GetDB 获取全局数据库连接
func GetDB() *sql.DB {
	return globalDB
}

// MustConnect 连接数据库，失败则 panic
func MustConnect() *sql.DB {
	conn, err := Connect()
	if err != nil {
		panic(fmt.Sprintf("failed to connect to database: %v", err))
	}
	globalDB = conn
	return conn
}

// RunMigrations 执行所有迁移文件（按文件名排序）
func RunMigrations(db *sql.DB, migrationsDir string) error {
	pattern := filepath.Join(migrationsDir, "*.up.sql")
	files, err := filepath.Glob(pattern)
	if err != nil {
		return fmt.Errorf("glob migrations: %w", err)
	}
	if len(files) == 0 {
		return fmt.Errorf("no migration files found in %s", migrationsDir)
	}
	sort.Strings(files)

	for _, f := range files {
		data, err := os.ReadFile(f)
		if err != nil {
			return fmt.Errorf("read %s: %w", filepath.Base(f), err)
		}

		if _, err := db.Exec(string(data)); err != nil {
			// 可能是表已存在，记录警告但不中断
			fmt.Printf("migration warning for %s: %v\n", filepath.Base(f), err)
		}
	}

	return nil
}
