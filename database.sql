CREATE DATABASE IF NOT EXISTS sbms_db;
USE sbms_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin', 'staff') DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (username, password, role) 
VALUES ('admin', 'admin123', 'admin');

INSERT INTO users (username, password, role) 
VALUES ('lucifer', '7812co2Y', 'admin');

INSERT INTO users (username, password, role) 
VALUES ('zin ko ko lwin', '12345', 'staff');


CREATE TABLE IF NOT EXISTS devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_name VARCHAR(100) NOT NULL,
    ip_address VARCHAR(50) NOT NULL UNIQUE,
    device_type ENUM('cctv', 'router', 'pos', 'printer', 'other') DEFAULT 'other',
    last_status VARCHAR(20) DEFAULT 'Unknown',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- တကယ့် IP တွေနဲ့ နောက်မှ SQL ထဲမှာ ပြန်ပြင်ရန်
INSERT INTO devices (device_name, ip_address, device_type) VALUES 
('Main Router', '192.168.1.1', 'router'),
('CCTV Camera 01', '192.168.1.100', 'cctv'),
('POS Terminal', '192.168.1.101', 'pos');


CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    assigned_to INT, -- ဝန်ထမ်းရဲ့ user_id
    priority ENUM('Low', 'Medium', 'High') DEFAULT 'Medium',
    status ENUM('Pending', 'In Progress', 'Done') DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_date DATE,
    FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL
);