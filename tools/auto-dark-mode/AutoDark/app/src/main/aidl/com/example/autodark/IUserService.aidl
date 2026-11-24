package com.example.autodark;

interface IUserService {
    // Reserved by Shizuku to stop the user service (LAST_CALL_TRANSACTION).
    void destroy() = 16777114;

    // Flip global system dark mode by running `cmd uimode night yes|no`
    // inside the shell-uid process Shizuku spawns. Returns true on success.
    boolean setNight(boolean on) = 1;
}
