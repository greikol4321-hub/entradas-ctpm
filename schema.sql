-- Sistema Entradas CTPM - MySQL 8.x
CREATE DATABASE IF NOT EXISTS entradas_ctpm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE entradas_ctpm;

-- Tabla principal: una fila = una entrada. Cubrimos los 3 estados del flujo.
CREATE TABLE IF NOT EXISTS entradas (
    id CHAR(36) PRIMARY KEY COMMENT 'UUID v4, tambien es el contenido del QR',
    nombre_completo VARCHAR(120) NOT NULL,
    cedula VARCHAR(20) NOT NULL,
    ubicacion ENUM('Gradas','Mesas') NOT NULL,
    mesa_numero SMALLINT DEFAULT NULL COMMENT 'NULL si Gradas, 1..20 si Mesas',
    monto INT NOT NULL DEFAULT 0 COMMENT '5000 Gradas / 10000 Mesas',
    telefono VARCHAR(20) DEFAULT NULL COMMENT 'WhatsApp donde se envía el QR',
    comprobante_path VARCHAR(255) NOT NULL COMMENT 'ruta relativa en /uploads',
    qr_path VARCHAR(255) DEFAULT NULL COMMENT 'ruta relativa en /static/qrcodes',
    estado ENUM('Pendiente','Aprobada','Usada') NOT NULL DEFAULT 'Pendiente',
    fecha_compra DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_aprobacion DATETIME DEFAULT NULL,
    fecha_uso DATETIME DEFAULT NULL,
    INDEX idx_estado (estado),
    INDEX idx_cedula (cedula),
    INDEX idx_mesa (mesa_numero)
) ENGINE=InnoDB;
-- Si ya existe la tabla, agrega telefono
-- ALTER TABLE entradas ADD COLUMN telefono VARCHAR(20) DEFAULT NULL AFTER ubicacion;

-- Tabla opcional para login admin si luego quieres agregar auth (no requerida para MVP)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('admin','portero') NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Admin por defecto: admin / admin123 (bcrypt) - cambia al deploy
-- INSERT INTO usuarios (username, password_hash, rol) VALUES ('admin', '$2b$12$...', 'admin');

-- Datos de ejemplo (opcional)
-- INSERT INTO entradas (id, nombre_completo, cedula, ubicacion, comprobante_path) VALUES (UUID(), 'Juan Perez', '1-2345-0678', 'Gradas', 'uploads/ejemplo.jpg');
