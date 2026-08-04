#Requires -Version 5.1

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("doctor", "bootstrap", "start", "finish", "update")]
    [string]$Command
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {

    "doctor" {
        & "$scriptRoot\doctor.ps1"
    }

    "bootstrap" {
        & "$scriptRoot\bootstrap-project.ps1"
    }

    "start" {
        & "$scriptRoot\start.ps1"
    }

    "finish" {
        & "$scriptRoot\finish.ps1"
    }

    "update" {
        & "$scriptRoot\update.ps1"
    }
}