/**
 * AKX Cashier - 收银台支付页面
 * 功能：二维码生成、倒计时、订单状态轮询、复制功能
 */
(function() {
    'use strict';

    // 配置由 HTML 页面通过 window.AKX_CONFIG 注入
    var CONFIG = window.AKX_CONFIG || {};
    
    // 默认配置
    var defaults = {
        pollInterval: 3000,           // 轮询间隔 3 秒
        pollIntervalFast: 1500,       // 快速轮询 1.5 秒（接近超时时）
        fastPollThreshold: 30,        // 剩余 30 秒时切换到快速轮询
        qrCodeSize: 246,
        apiEndpoint: "/pay/api/status/"
    };
    
    // 合并配置
    CONFIG = $.extend({}, defaults, CONFIG);

    // ==================== 状态 ====================
    var state = {
        timer: null,
        countdownTimer: null,
        remainingSeconds: CONFIG.remainingSeconds || 0,
        isPolling: false,
        lastStatus: null
    };

    // ==================== 工具函数 ====================
    function formatTime(seconds) {
        var min = Math.floor(seconds / 60);
        var sec = seconds % 60;
        return {
            min: min < 10 ? "0" + min : String(min),
            sec: sec < 10 ? "0" + sec : String(sec)
        };
    }

    function showToast(options) {
        if (typeof $.toast !== 'function') {
            console.log(options.heading || options.text);
            return;
        }
        $.toast($.extend({
            position: "top-center",
            hideAfter: 1500
        }, options));
    }

    // ==================== 二维码 ====================
    function initQRCode() {
        if (typeof QRious === 'undefined') {
            console.error('QRious 库未加载');
            return;
        }
        
        try {
            new QRious({
                element: document.getElementById('qrcode'),
                size: CONFIG.qrCodeSize,
                value: CONFIG.walletAddress,
                level: 'M'
            });
        } catch (e) {
            console.error('QR Code 生成失败:', e);
        }
    }

    // ==================== 页面状态切换 ====================
    function handleSuccess() {
        cleanup();
        showToast({
            heading: "支付成功",
            text: "订单已完成，感谢您的使用！",
            bgColor: "#009393",
            textColor: "#fff",
            icon: "success"
        });
        // 延迟后刷新页面，后端会返回 success.html
        setTimeout(function() {
            location.reload();
        }, 1000);
    }

    function handleExpired() {
        cleanup();
        // 刷新页面，后端会返回 expired.html
        location.reload();
    }

    // ==================== 状态轮询 ====================
    function checkStatus() {
        if (state.isPolling || !CONFIG.orderNo) return;
        state.isPolling = true;

        $.ajax({
            url: CONFIG.apiEndpoint + CONFIG.orderNo,
            method: 'GET',
            dataType: 'json',
            timeout: 5000
        })
        .done(function(data) {
            if (!data || !data.status) return;
            
            // 状态变化时才处理
            if (data.status !== state.lastStatus) {
                state.lastStatus = data.status;
                
                switch (data.status) {
                    case 'success':
                    case 'completed':
                        handleSuccess();
                        break;
                    case 'expired':
                    case 'failed':
                    case 'cancelled':
                        handleExpired();
                        break;
                    case 'confirming':
                        // 区块确认中，可以显示确认进度
                        break;
                }
            }
        })
        .fail(function(xhr, status, error) {
            // 网络错误静默处理，继续轮询
            console.warn('状态查询失败:', status, error);
        })
        .always(function() {
            state.isPolling = false;
        });
    }

    // ==================== 倒计时 ====================
    function updateCountdown() {
        if (state.remainingSeconds < 0) {
            handleExpired();
            return;
        }

        var time = formatTime(state.remainingSeconds);
        $(".min").text(time.min);
        $(".sec").text(time.sec);
        state.remainingSeconds--;
    }

    function startCountdown() {
        // 立即更新一次
        updateCountdown();
        
        // 每秒更新倒计时
        state.countdownTimer = setInterval(function() {
            updateCountdown();
        }, 1000);
    }

    function startPolling() {
        // 立即检查一次
        checkStatus();

        // 定时轮询
        function poll() {
            // 根据剩余时间调整轮询频率
            var interval = state.remainingSeconds <= CONFIG.fastPollThreshold 
                ? CONFIG.pollIntervalFast 
                : CONFIG.pollInterval;
            
            state.timer = setTimeout(function() {
                checkStatus();
                poll();
            }, interval);
        }
        
        poll();
    }

    // ==================== 复制功能 ====================
    function initClipboard() {
        if (typeof ClipboardJS === 'undefined') {
            console.error('ClipboardJS 库未加载');
            return;
        }
        
        var clipboard = new ClipboardJS(".clipboard-btn");

        clipboard.on("success", function(e) {
            showToast({
                heading: "复制成功",
                text: '<p style="white-space:normal;word-break:break-all;">' + e.text + '</p>',
                bgColor: "#161141",
                textColor: "#0f8",
                icon: "success"
            });
            e.clearSelection();
        });

        clipboard.on("error", function() {
            showToast({
                text: "复制失败，请手动复制",
                bgColor: "#ef4444",
                textColor: "#fff",
                hideAfter: 3000
            });
        });
    }

    // ==================== 清理 ====================
    function cleanup() {
        if (state.timer) {
            clearTimeout(state.timer);
            state.timer = null;
        }
        if (state.countdownTimer) {
            clearInterval(state.countdownTimer);
            state.countdownTimer = null;
        }
    }

    // ==================== 页面可见性处理 ====================
    function handleVisibilityChange() {
        if (document.hidden) {
            // 页面不可见时暂停轮询（保留倒计时）
            if (state.timer) {
                clearTimeout(state.timer);
                state.timer = null;
            }
        } else {
            // 页面可见时恢复轮询并立即检查状态
            if (!state.timer && state.remainingSeconds > 0) {
                checkStatus();
                startPolling();
            }
        }
    }

    // ==================== 初始化 ====================
    function init() {
        initQRCode();
        initClipboard();
        startCountdown();
        startPolling();

        // 监听页面可见性变化
        document.addEventListener('visibilitychange', handleVisibilityChange);

        // 页面卸载时清理
        $(window).on('beforeunload', cleanup);
    }

    // DOM Ready
    $(document).ready(init);
})();
