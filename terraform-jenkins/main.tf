terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "Jenkins-DevOps-RG" 
    storage_account_name = "devopsmcpstate" 
    container_name       = "tfstate"
    key                  = "terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "japaneast"
}

variable "admin_username" {
  description = "Admin username for the Jenkins VM"
  type        = string
  default     = "azureuser"
}

variable "public_key_path" {
  description = "Path to the SSH public key used for VM login"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "admin_allowed_cidrs" {
  description = "Allowed CIDR blocks for SSH access"
  type        = list(string)

  validation {
    condition     = length(var.admin_allowed_cidrs) > 0
    error_message = "admin_allowed_cidrs must include at least one trusted CIDR block."
  }
}

variable "jenkins_allowed_cidrs" {
  description = "Allowed CIDR blocks for Jenkins web access"
  type        = list(string)

  validation {
    condition     = length(var.jenkins_allowed_cidrs) > 0
    error_message = "jenkins_allowed_cidrs must include at least one trusted CIDR block."
  }
}

# 1. Tạo Resource Group (Nhóm tài nguyên)
resource "azurerm_resource_group" "jenkins_rg" {
  name     = "Jenkins-DevOps-RG"
  location = var.location
}

# 2. Tạo Mạng ảo (VNet & Subnet)
resource "azurerm_virtual_network" "jenkins_vnet" {
  name                = "jenkins-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.jenkins_rg.location
  resource_group_name = azurerm_resource_group.jenkins_rg.name
}

resource "azurerm_subnet" "jenkins_subnet" {
  name                 = "jenkins-subnet"
  resource_group_name  = azurerm_resource_group.jenkins_rg.name
  virtual_network_name = azurerm_virtual_network.jenkins_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# 3. Tạo IP Public để truy cập Web Jenkins từ bên ngoài
resource "azurerm_public_ip" "jenkins_pip" {
  name                = "jenkins-pip"
  location            = azurerm_resource_group.jenkins_rg.location
  resource_group_name = azurerm_resource_group.jenkins_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# 4. Tạo Card mạng (Network Interface)
resource "azurerm_network_interface" "jenkins_nic" {
  name                = "jenkins-nic"
  location            = azurerm_resource_group.jenkins_rg.location
  resource_group_name = azurerm_resource_group.jenkins_rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.jenkins_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.jenkins_pip.id
  }
}

# 5. Khởi tạo Máy ảo Ubuntu cho Jenkins
resource "azurerm_linux_virtual_machine" "jenkins_vm" {
  name                = "jenkins-server"
  resource_group_name = azurerm_resource_group.jenkins_rg.name
  location            = azurerm_resource_group.jenkins_rg.location
  size                = "Standard_D2s_v3"
  admin_username      = var.admin_username
  disable_password_authentication = true
  
  network_interface_ids = [
    azurerm_network_interface.jenkins_nic.id,
  ]

  # Tự động gắn khóa SSH vừa tạo
  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }
}

# In ra địa chỉ IP của server sau khi tạo xong
output "jenkins_public_ip" {
  value = azurerm_linux_virtual_machine.jenkins_vm.public_ip_address
}

# 6. Tạo Network Security Group (Tường lửa)
resource "azurerm_network_security_group" "jenkins_nsg" {
  name                = "jenkins-nsg"
  location            = azurerm_resource_group.jenkins_rg.location
  resource_group_name = azurerm_resource_group.jenkins_rg.name

  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.admin_allowed_cidrs
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-jenkins"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8080"
    source_address_prefixes    = var.jenkins_allowed_cidrs
    destination_address_prefix = "*"
  }
}

# 7. Gắn Tường lửa vào Card mạng của máy ảo
resource "azurerm_network_interface_security_group_association" "nsg_assoc" {
  network_interface_id      = azurerm_network_interface.jenkins_nic.id
  network_security_group_id = azurerm_network_security_group.jenkins_nsg.id
}
