$log = "C:\Users\corba\Downloads\Compu\boot_check.txt"
"--- Fix Boot ---" | Out-File $log

# Ensure boot files are safely on the C: drive's own EFI/system partition
bcdboot C:\Windows /f ALL | Out-File $log -Append

"--- Disk 2 Cleanup ---" | Out-File $log -Append
"select disk 2`nselect partition 1`ndelete partition override`nselect partition 2`ndelete partition override`nselect partition 3`ndelete partition override`nclean`nconvert gpt`ncreate partition primary`nformat fs=ntfs label=`"NVMe_Ready`" quick`nassign" | Out-File C:\Users\corba\Downloads\Compu\clean2.txt
diskpart /s C:\Users\corba\Downloads\Compu\clean2.txt | Out-File $log -Append
