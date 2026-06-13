/**
 * ModernImageEditor - 专业图片编辑器
 * 一个基于Canvas的现代化图片编辑工具
 */

 class ModernImageEditor {
    constructor() {
        // 基础设置
        this.canvas = document.getElementById("imageCanvas");
        this.ctx = this.canvas.getContext("2d");
        this.image = new Image;
        this.fileInput = document.createElement("input");
        this.fileInput.type = "file";
        this.fileInput.accept = "image/*";
        this.fileInput.style.display = "none";
        document.body.appendChild(this.fileInput);
        
        // 添加文件选择事件监听
        this.fileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files[0]) {
                this.loadImageFromFile(e.target.files[0]);
            }
        });
        
        // 工具状态
        this.currentTool = "select";
        this.isDrawing = false;
        this.startX = 0;
        this.startY = 0;
        
        // 元素管理
        this.elements = [];
        this.selectedElement = null;
        this.selectedElements = []; // 多选元素数组
        this.isMultiSelecting = false; // 是否正在框选
        this.selectionBox = null; // 选框区域
        this.history = [];
        this.historyIndex = -1;
        
        // 拖拽和缩放状态
        this.isDragging = false;
        this.dragOffset = {x: 0, y: 0};
        this.isDraggingMultiple = false; // 多选拖动状态
        this.isResizing = false;
        this.resizeHandle = null;
        
        // 剪贴板功能
        this.clipboard = []; // 存储复制的元素
        this.clipboardOffset = {x: 10, y: 10}; // 粘贴时的偏移量
        
        // 裁剪功能
        this.cropArea = null;
        this.isCropping = false;
        
        // 画笔功能
        this.brushStrokes = [];
        this.currentStroke = null;
        this.currentMosaicStroke = null;
        
        // 序号功能
        this.numberCounter = 1;
        
        // 网格功能
        this.showGrid = false;
        this.gridSize = 50; // 网格间距
        
        // 缩放设置
        this.displayScale = 1;
        this.zoomScale = 1;
        this.minZoom = 0.1;
        this.maxZoom = 5;
        this.zoomStep = 0.1;
        
        // 工具设置
        this.settings = {
            text: {
                content: "文字",
                color: "#ff0000",
                size: 22,
                bold: false,
                italic: false,
                underline: false
            },
            brush: {
                color: "#ff0000",
                size: 6
            },
            ellipse: {
                color: "#ff0000",
                stroke: 6
            },
            rectangle: {
                color: "#ff0000",
                stroke: 2
            },
            arrow: {
                color: "#ff0000",
                stroke: 3
            },
            highlight: {
                color: "#ffff00",
                opacity: 0.3
            },
            mosaic: {
                intensity: 10,
                size: 20
            }
        };
        
        this.init();
    }

    /**
     * 初始化编辑器
     */
    init() {
        // 检查URL查询参数中的图片地址和鼠标坐标
        const urlParams = new URLSearchParams(window.location.search);
        const imageUrl = urlParams.get('url');
        const mouseParam = urlParams.get('mouse');
        
        if (imageUrl) {
            // 如果有URL参数，加载指定图片
            console.log('从URL参数加载图片:', imageUrl);
            this.loadImageFromUrl(imageUrl, mouseParam);
        } else {
            // 加载保存的数据
            var editorData = sessionStorage.getItem("editorData");
            if (editorData) {
                this.editorData = JSON.parse(editorData);
                this.loadImage(this.editorData.screenshot);
            } else {
                // 如果没有保存的数据，显示拖拽上传区域
                this.showDragDropArea();
            }
        }
        
        this.setupEventListeners();
        this.setupToolbar();
        this.saveState();
    }

    /**
     * 加载图片到画布
     * @param {string} imageSrc - 图片数据URL
     */
    loadImage(imageSrc) {
        this.image.onload = () => {
            this.backgroundImage = this.image;
            var dimensions = {width: this.image.width, height: this.image.height};
            
            this.canvas.width = dimensions.width;
            this.canvas.height = dimensions.height;
            this.zoomScale = 1;
            this.updateCanvasSize();
            this.render();
        };
        this.image.src = imageSrc;
    }

    /**
     * 从URL加载图片到画布
     * @param {string} imageUrl - 图片URL地址
     * @param {string} mouseParam - 鼠标坐标参数字符串 (可选)
     */
    loadImageFromUrl(imageUrl, mouseParam = null) {
        // 创建一个新的图片对象来加载远程图片
        const remoteImage = new Image();
        
        // 设置跨域属性，允许加载外部图片
        remoteImage.crossOrigin = 'anonymous';
        
        remoteImage.onload = () => {
            console.log('图片加载成功:', imageUrl);
            this.backgroundImage = remoteImage;
            var dimensions = {width: remoteImage.width, height: remoteImage.height};
            
            this.canvas.width = dimensions.width;
            this.canvas.height = dimensions.height;
            this.zoomScale = 1;
            this.updateCanvasSize();
            this.render();
            
            // 隐藏拖拽上传区域
            this.hideDragDropArea();
            
            // 显示成功提示
            this.showNotification('图片加载成功！', 'success');
            
            // 如果有鼠标坐标参数，自动生成矩形
            if (mouseParam) {
                this.generateRectFromMouseParam(mouseParam);
            }
        };
        
        remoteImage.onerror = () => {
            console.error('图片加载失败:', imageUrl);
            this.showNotification('图片加载失败，请检查URL地址是否正确', 'error');
            
            // 加载失败时显示默认画布
            this.canvas.width = 800;
            this.canvas.height = 600;
            this.ctx.fillStyle = "#ffffff";
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            this.render();
        };
        
        remoteImage.src = imageUrl;
    }

    /**
     * 显示通知消息
     * @param {string} message - 消息内容
     * @param {string} type - 消息类型 ('success', 'error', 'info')
     */
    showNotification(message, type = 'info') {
        // 移除已存在的通知
        const existingNotification = document.querySelector('.notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        
        // 设置样式
        const colors = {
            success: '#28a745',
            error: '#dc3545',
            info: '#007bff'
        };
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${colors[type]};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            font-size: 14px;
            font-weight: 500;
            animation: slideIn 0.3s ease;
        `;
        
        // 添加滑入动画
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
        `;
        document.head.appendChild(style);
        
        document.body.appendChild(notification);
        
        // 3秒后自动移除
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 3000);
    }

    /**
     * 设置事件监听器
     */
    setupEventListeners() {
        // 画布事件
        this.canvas.addEventListener("mousedown", this.handleMouseDown.bind(this));
        this.canvas.addEventListener("mousemove", this.handleMouseMove.bind(this));
        this.canvas.addEventListener("mouseup", this.handleMouseUp.bind(this));
        this.canvas.addEventListener("click", this.handleClick.bind(this));
        this.canvas.addEventListener("dblclick", this.handleDoubleClick.bind(this));
        this.canvas.addEventListener("wheel", this.handleWheel.bind(this));
        
        // 文档事件
        document.addEventListener("keydown", this.handleKeyDown.bind(this));
        
        // 拖拽上传事件
        this.setupDragAndDrop();
        
        // 按钮事件
        document.getElementById("uploadBtn").addEventListener("click", this.handleUpload.bind(this));
        document.getElementById("saveBtn").addEventListener("click", this.saveImage.bind(this));
        document.getElementById("downloadBtn").addEventListener("click", this.downloadImage.bind(this));
        document.getElementById("deleteElement").addEventListener("click", this.deleteSelectedElement.bind(this));
        
        // JSON按钮事件
        document.getElementById("exportJsonBtn").addEventListener("click", this.exportElementsToJson.bind(this));
        document.getElementById("importJsonBtn").addEventListener("click", () => {
            document.getElementById("jsonFileInput").click();
        });
        document.getElementById("jsonFileInput").addEventListener("change", this.importElementsFromJson.bind(this));
        
        // 截图管理按钮事件
        document.getElementById("viewScreenshotsBtn").addEventListener("click", this.showScreenshotsDrawer.bind(this));
        document.getElementById("closeDrawerBtn").addEventListener("click", this.hideScreenshotsDrawer.bind(this));
        document.getElementById("exportAllScreenshotsBtn").addEventListener("click", this.exportAllScreenshots.bind(this));
        
        // 点击遮罩层关闭抽屉
        document.getElementById("screenshotsOverlay").addEventListener("click", (e) => {
            if (e.target === e.currentTarget) {
                this.hideScreenshotsDrawer();
            }
        });
    }

    /**
     * 设置工具栏
     */
    setupToolbar() {
        // 工具按钮事件
        document.querySelectorAll(".tool-item").forEach(button => {
            button.addEventListener("click", () => {
                var tool = button.dataset.tool;
                if (tool === "undo") {
                    this.undo();
                } else if (tool === "grid") {
                    this.toggleGrid();
                } else {
                    this.setTool(tool);
                    this.updateToolbar(tool);
                }
            });
        });
        
        // 设置各种工具的控制面板
        this.setupTextControls();
        this.setupBrushControls();
        this.setupEllipseControls();
        this.setupRectangleControls();
        this.setupArrowControls();
        this.setupHighlightControls();
        this.setupNumberControls();
        this.setupMosaicControls();
        
        this.updateToolbar("select");
    }

    /**
     * 设置文字工具控制面板
     */
    setupTextControls() {
        var colorInput = document.getElementById("textColor");
        var sizeInput = document.getElementById("textSize");
        let sizeDisplay = document.getElementById("textSizeDisplay");
        var boldBtn = document.getElementById("textBold");
        var italicBtn = document.getElementById("textItalic");
        var underlineBtn = document.getElementById("textUnderline");
        
        colorInput.addEventListener("change", event => {
            this.settings.text.color = event.target.value;
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "text") {
                this.selectedElement.color = event.target.value;
                this.render();
            }
        });
        
        sizeInput.addEventListener("input", event => {
            this.settings.text.size = parseInt(event.target.value);
            sizeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "text") {
                this.selectedElement.size = parseInt(event.target.value);
                this.render();
            }
        });
        
        boldBtn.addEventListener("click", () => {
            this.settings.text.bold = !this.settings.text.bold;
            boldBtn.classList.toggle("active", this.settings.text.bold);
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "text") {
                this.selectedElement.bold = this.settings.text.bold;
                this.render();
            }
        });
        
        italicBtn.addEventListener("click", () => {
            this.settings.text.italic = !this.settings.text.italic;
            italicBtn.classList.toggle("active", this.settings.text.italic);
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "text") {
                this.selectedElement.italic = this.settings.text.italic;
                this.render();
            }
        });
        
        underlineBtn.addEventListener("click", () => {
            this.settings.text.underline = !this.settings.text.underline;
            underlineBtn.classList.toggle("active", this.settings.text.underline);
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "text") {
                this.selectedElement.underline = this.settings.text.underline;
                this.render();
            }
        });
    }

    /**
     * 设置画笔工具控制面板
     */
    setupBrushControls() {
        var colorInput = document.getElementById("brushColor");
        var sizeInput = document.getElementById("brushSize");
        let sizeDisplay = document.getElementById("brushSizeDisplay");
        
        colorInput.addEventListener("change", event => {
            this.settings.brush.color = event.target.value;
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "brush") {
                this.selectedElement.color = event.target.value;
                this.render();
            }
        });
        
        sizeInput.addEventListener("input", event => {
            this.settings.brush.size = parseInt(event.target.value);
            sizeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "brush") {
                this.selectedElement.size = parseInt(event.target.value);
                this.render();
            }
        });
    }

    /**
     * 设置椭圆工具控制面板
     */
    setupEllipseControls() {
        var colorInput = document.getElementById("ellipseColor");
        var strokeInput = document.getElementById("ellipseStroke");
        let strokeDisplay = document.getElementById("ellipseStrokeDisplay");
        
        colorInput.addEventListener("change", event => {
            this.settings.ellipse.color = event.target.value;
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "shape" && this.selectedElement.shapeType === "ellipse") {
                this.selectedElement.color = event.target.value;
                this.render();
            }
        });
        
        strokeInput.addEventListener("input", event => {
            this.settings.ellipse.stroke = parseInt(event.target.value);
            strokeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "shape" && this.selectedElement.shapeType === "ellipse") {
                this.selectedElement.stroke = parseInt(event.target.value);
                this.render();
            }
        });
    }

    /**
     * 设置矩形工具控制面板
     */
    setupRectangleControls() {
        var colorInput = document.getElementById("rectangleColor");
        var strokeInput = document.getElementById("rectangleStroke");
        let strokeDisplay = document.getElementById("rectangleStrokeDisplay");
        
        colorInput.addEventListener("change", event => {
            this.settings.rectangle.color = event.target.value;
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "shape" && this.selectedElement.shapeType === "rect") {
                this.selectedElement.color = event.target.value;
                this.render();
            }
        });
        
        strokeInput.addEventListener("input", event => {
            this.settings.rectangle.stroke = parseInt(event.target.value);
            strokeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "shape" && this.selectedElement.shapeType === "rect") {
                this.selectedElement.stroke = parseInt(event.target.value);
                this.render();
            }
        });
    }

    /**
     * 设置高亮工具控制面板（暂无特殊设置）
     */
    setupHighlightControls() {
        // 暂无特殊设置
    }

    /**
     * 设置序号工具控制面板
     */
    setupNumberControls() {
        let numberButtons = document.querySelectorAll(".number-button");
        numberButtons.forEach(button => {
            button.addEventListener("click", () => {
                numberButtons.forEach(btn => btn.classList.remove("active"));
                button.classList.add("active");
                this.numberCounter = parseInt(button.dataset.number);
            });
        });
    }

    /**
     * 设置马赛克工具控制面板
     */
    setupMosaicControls() {
        var intensityInput = document.getElementById("mosaicIntensity");
        let intensityDisplay = document.getElementById("mosaicIntensityDisplay");
        var sizeInput = document.getElementById("mosaicSize");
        let sizeDisplay = document.getElementById("mosaicSizeDisplay");
        
        intensityInput.addEventListener("input", event => {
            this.settings.mosaic.intensity = parseInt(event.target.value);
            intensityDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "mosaic") {
                this.selectedElement.intensity = parseInt(event.target.value);
                this.render();
            }
        });
        
        sizeInput.addEventListener("input", event => {
            this.settings.mosaic.size = parseInt(event.target.value);
            sizeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "mosaic") {
                this.selectedElement.size = parseInt(event.target.value);
                this.render();
            }
        });
    }

    /**
     * 设置箭头工具控制面板
     */
    setupArrowControls() {
        var colorInput = document.getElementById("arrowColor");
        var strokeInput = document.getElementById("arrowStroke");
        let strokeDisplay = document.getElementById("arrowStrokeDisplay");
        
        colorInput.addEventListener("change", event => {
            this.settings.arrow.color = event.target.value;
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "arrow") {
                this.selectedElement.color = event.target.value;
                this.render();
            }
        });
        
        strokeInput.addEventListener("input", event => {
            this.settings.arrow.stroke = parseInt(event.target.value);
            strokeDisplay.textContent = event.target.value + "px";
            // 同步更新选中元素
            if (this.selectedElement && this.selectedElement.type === "arrow") {
                this.selectedElement.stroke = parseInt(event.target.value);
                this.render();
            }
        });
    }

    /**
     * 设置当前工具
     * @param {string} tool - 工具名称
     */
    setTool(tool) {
        this.currentTool = tool;
        this.selectedElement = null;
        this.hidePropertyPanel();
        this.hideCropConfirmation();
        
        // 重置裁剪状态
        if (tool !== "crop") {
            this.cropArea = null;
            this.isCropping = false;
        }
        
        this.updateToolbar(tool);
        
        // 更新工具选项显示
        this.updateToolOptionsForSelection();
        
        // 设置鼠标样式
        switch(tool) {
            case "brush":
            case "arrow":
                this.canvas.style.cursor = "crosshair";
                break;
            case "text":
            case "number":
                this.canvas.style.cursor = "text";
                break;
            case "crop":
                this.canvas.style.cursor = "crosshair";
                break;
            default:
                this.canvas.style.cursor = "default";
        }
        
        this.render();
    }

    /**
     * 更新工具栏状态
     * @param {string} activeTool - 当前激活的工具
     */
    updateToolbar(activeTool) {
        // 更新工具按钮状态
        document.querySelectorAll(".tool-item").forEach(button => {
            button.classList.toggle("active", button.dataset.tool === activeTool);
        });
        
        // 注意：不在这里处理选项面板的显示，让 updateToolOptionsForSelection 统一处理
        // 这避免了与元素选择逻辑的冲突
    }

    /**
     * 同步选中元素的值到工具选项面板控件
     * @param {Object} element - 选中的元素
     */
    syncElementValuesToControls(element) {
        if (!element) return;
        
        var elementType = element.type;
        
        switch (elementType) {
            case "text":
                if (element.color) {
                    var colorInput = document.getElementById("textColor");
                    if (colorInput) colorInput.value = element.color;
                }
                if (element.size) {
                    var sizeInput = document.getElementById("textSize");
                    var sizeDisplay = document.getElementById("textSizeDisplay");
                    if (sizeInput) sizeInput.value = element.size;
                    if (sizeDisplay) sizeDisplay.textContent = element.size + "px";
                }
                if (element.bold !== undefined) {
                    var boldBtn = document.getElementById("textBold");
                    if (boldBtn) boldBtn.classList.toggle("active", element.bold);
                }
                if (element.italic !== undefined) {
                    var italicBtn = document.getElementById("textItalic");
                    if (italicBtn) italicBtn.classList.toggle("active", element.italic);
                }
                if (element.underline !== undefined) {
                    var underlineBtn = document.getElementById("textUnderline");
                    if (underlineBtn) underlineBtn.classList.toggle("active", element.underline);
                }
                break;
                
            case "brush":
                if (element.color) {
                    var colorInput = document.getElementById("brushColor");
                    if (colorInput) colorInput.value = element.color;
                }
                if (element.size) {
                    var sizeInput = document.getElementById("brushSize");
                    var sizeDisplay = document.getElementById("brushSizeDisplay");
                    if (sizeInput) sizeInput.value = element.size;
                    if (sizeDisplay) sizeDisplay.textContent = element.size + "px";
                }
                break;
                
            case "arrow":
                if (element.color) {
                    var colorInput = document.getElementById("arrowColor");
                    if (colorInput) colorInput.value = element.color;
                }
                if (element.stroke) {
                    var strokeInput = document.getElementById("arrowStroke");
                    var strokeDisplay = document.getElementById("arrowStrokeDisplay");
                    if (strokeInput) strokeInput.value = element.stroke;
                    if (strokeDisplay) strokeDisplay.textContent = element.stroke + "px";
                }
                break;
                
            case "shape":
                var shapeType = element.shapeType;
                if (shapeType === "rect") {
                    if (element.color) {
                        var colorInput = document.getElementById("rectangleColor");
                        if (colorInput) colorInput.value = element.color;
                    }
                    if (element.stroke) {
                        var strokeInput = document.getElementById("rectangleStroke");
                        var strokeDisplay = document.getElementById("rectangleStrokeDisplay");
                        if (strokeInput) strokeInput.value = element.stroke;
                        if (strokeDisplay) strokeDisplay.textContent = element.stroke + "px";
                    }
                } else if (shapeType === "ellipse") {
                    if (element.color) {
                        var colorInput = document.getElementById("ellipseColor");
                        if (colorInput) colorInput.value = element.color;
                    }
                    if (element.stroke) {
                        var strokeInput = document.getElementById("ellipseStroke");
                        var strokeDisplay = document.getElementById("ellipseStrokeDisplay");
                        if (strokeInput) strokeInput.value = element.stroke;
                        if (strokeDisplay) strokeDisplay.textContent = element.stroke + "px";
                    }
                }
                break;
                
            case "mosaic":
                if (element.intensity) {
                    var intensityInput = document.getElementById("mosaicIntensity");
                    var intensityDisplay = document.getElementById("mosaicIntensityDisplay");
                    if (intensityInput) intensityInput.value = element.intensity;
                    if (intensityDisplay) intensityDisplay.textContent = element.intensity + "px";
                }
                if (element.size) {
                    var sizeInput = document.getElementById("mosaicSize");
                    var sizeDisplay = document.getElementById("mosaicSizeDisplay");
                    if (sizeInput) sizeInput.value = element.size;
                    if (sizeDisplay) sizeDisplay.textContent = element.size + "px";
                }
                break;
        }
    }

    /**
     * 根据选择状态更新工具选项显示
     * 当选择模式下有元素选中时，显示元素选项；没有选中时显示select选项
     */
    updateToolOptionsForSelection() {
        // 调试输出
        console.log('=== 工具选项更新 ===');
        console.log('currentTool:', this.currentTool);
        console.log('selectedElement:', this.selectedElement);
        if (this.selectedElement) {
            console.log('selectedElement.type:', this.selectedElement.type);
        }
        
        // 隐藏所有工具选项面板
        document.querySelectorAll(".tool-options").forEach(panel => {
            panel.classList.remove("active");
        });

        if (this.currentTool === "select") {
            if (this.selectedElement) {
                // 如果有元素选中，显示对应元素的选项面板
                var elementType = this.selectedElement.type;
                var optionsId = elementType + "Options";
                
                // 特殊处理：shape类型需要根据shapeType选择正确的选项面板
                if (elementType === "shape") {
                    var shapeType = this.selectedElement.shapeType;
                    if (shapeType === "rect") {
                        optionsId = "rectangleOptions";
                        console.log(`🎯 矩形元素: 显示 ${optionsId}`);
                    } else if (shapeType === "ellipse") {
                        optionsId = "ellipseOptions";
                        console.log(`🎯 椭圆元素: 显示 ${optionsId}`);
                    } else {
                        console.warn(`⚠️ 未知shapeType: ${shapeType}，使用默认 ${optionsId}`);
                    }
                } else {
                    console.log(`🎯 尝试显示 ${optionsId} (基于 ${elementType} 元素)`);
                }
                
                var elementPanel = document.getElementById(optionsId);
                if (elementPanel) {
                    elementPanel.classList.add("active");
                    console.log(`✅ 成功显示 ${optionsId}`);
                    // 同步显示选中元素的值
                    this.syncElementValuesToControls(this.selectedElement);
                } else {
                    console.error(`❌ 未找到选项面板: ${optionsId}`);
                }
            } else {
                // 如果没有元素选中，显示select选项
                console.log('🎯 显示 selectOptions (无元素选中)');
                var selectPanel = document.getElementById("selectOptions");
                if (selectPanel) {
                    selectPanel.classList.add("active");
                    console.log('✅ 成功显示 selectOptions');
                } else {
                    console.error('❌ 未找到 selectOptions 面板');
                }
            }
        } else {
            // 非选择模式，显示当前工具的选项面板
            var currentPanel = document.getElementById(this.currentTool + "Options");
            if (currentPanel) {
                currentPanel.classList.add("active");
                console.log(`✅ 成功显示 ${this.currentTool}Options (非选择模式)`);
            } else {
                console.error(`❌ 未找到 ${this.currentTool}Options 面板`);
            }
        }
    }

    /**
     * 获取鼠标在画布上的坐标
     * @param {MouseEvent} event - 鼠标事件
     * @returns {Object} 坐标对象 {x, y}
     */
    getMousePos(event) {
        var canvasRect = this.canvas.getBoundingClientRect();
        return {
            x: (event.clientX - canvasRect.left) / this.displayScale,
            y: (event.clientY - canvasRect.top) / this.displayScale
        };
    }

    // ===================== 鼠标事件处理 =====================

    /**
     * 处理鼠标按下事件
     * @param {MouseEvent} event - 鼠标事件
     */
    handleMouseDown(event) {
        var mousePos = this.getMousePos(event);
        
        this.startX = mousePos.x;
        this.startY = mousePos.y;
        this.isDrawing = true;
        
        switch(this.currentTool) {
            case "select":
                this.handleSelectMouseDown(mousePos);
                break;
            case "crop":
                this.handleCropMouseDown(mousePos);
                break;
            case "brush":
                this.handleBrushMouseDown(mousePos);
                break;
            case "arrow":
            case "ellipse":
            case "rectangle":
            case "highlight":
                // 这些工具在鼠标移动时才处理
                break;
            case "mosaic":
                this.handleMosaicMouseDown(mousePos);
                break;
        }
    }

    /**
     * 处理鼠标移动事件
     * @param {MouseEvent} event - 鼠标事件
     */
    handleMouseMove(event) {
        var mousePos = this.getMousePos(event);
        
        // 选择工具的鼠标移动处理
        if (this.currentTool === "select") {
            // 多选拖动优先处理
            if (this.isDraggingMultiple) {
                this.handleSelectMouseMove(mousePos);
                return;
            }
            
            if (this.isMultiSelecting) {
                // 正在矩形选择，调用矩形选择处理
                this.handleSelectMouseMove(mousePos);
                return;
            }
            
            if (this.selectedElement && (this.isDragging || this.isResizing)) {
                // 正在拖动或缩放，调用对应的处理方法
                if (this.isResizing && this.resizeHandle) {
                    this.resizeElement(mousePos);
                    this.render();
                    this.updatePropertyPanelValues();
                } else if (this.isDragging) {
                    this.handleSelectMouseMove(mousePos);
                }
            } else if ((this.selectedElement || this.selectedElements.length > 0) && !this.isDrawing) {
                // 已选择元素但没有操作，更新鼠标样式
                var resizeHandle = null;
                if (this.selectedElement) {
                    resizeHandle = this.getResizeHandle(mousePos.x, mousePos.y, this.selectedElement);
                }
                this.updateCursor(resizeHandle);
            }
        } else if (this.isDrawing) {
            switch(this.currentTool) {
                case "crop":
                    this.handleCropMouseMove(mousePos);
                    break;
                case "brush":
                    this.handleBrushMouseMove(mousePos);
                    break;
                case "ellipse":
                case "rectangle":
                case "arrow":
                    this.handleShapeMouseMove(mousePos);
                    break;
                case "highlight":
                    this.handleHighlightMouseMove(mousePos);
                    break;
                case "mosaic":
                    this.handleMosaicMouseMove(mousePos);
                    break;
            }
        }
    }

    /**
     * 处理鼠标释放事件
     * @param {MouseEvent} event - 鼠标事件
     */
    handleMouseUp(event) {
        if (this.isDrawing) {
            var mousePos = this.getMousePos(event);
            
            switch(this.currentTool) {
                case "select":
                    this.handleSelectMouseUp(mousePos);
                    break;
                case "crop":
                    this.handleCropMouseUp(mousePos);
                    break;
                case "brush":
                    this.handleBrushMouseUp(mousePos);
                    break;
                case "ellipse":
                case "rectangle":
                case "arrow":
                    this.handleShapeMouseUp(mousePos);
                    break;
                case "highlight":
                    this.handleHighlightMouseUp(mousePos);
                    break;
                case "mosaic":
                    this.handleMosaicMouseUp(mousePos);
                    break;
            }
            
            this.isDrawing = false;
            this.isDragging = false;
            this.isDraggingMultiple = false;
            this.isResizing = false;
        }
    }

    /**
     * 处理点击事件
     * @param {MouseEvent} event - 鼠标事件
     */
    handleClick(event) {
        var mousePos = this.getMousePos(event);
        
        if (this.currentTool === "text") {
            this.addText(mousePos.x, mousePos.y);
        } else if (this.currentTool === "number") {
            this.addNumber(mousePos.x, mousePos.y);
        }
    }

    /**
     * 处理双击事件
     * @param {MouseEvent} event - 鼠标事件
     */
    handleDoubleClick(event) {
        var mousePos = this.getMousePos(event);
        var element = this.getElementAtPoint(mousePos.x, mousePos.y);
        
        if (element) {
            // 确保元素被选中
            this.selectedElement = element;
            
            if (element.type === "text") {
                this.editTextElement(element);
                // 双击文本后显示属性面板
                this.showPropertyPanel(element);
            } else {
                // 其他元素双击时也显示属性面板
                this.showPropertyPanel(element);
            }
        }
        
        this.render();
    }

    /**
     * 处理键盘事件
     * @param {KeyboardEvent} event - 键盘事件
     */
    handleKeyDown(event) {
        // 如果当前有输入框获得焦点，不处理快捷键（避免与输入冲突）
        if (document.activeElement && 
            (document.activeElement.tagName === 'INPUT' || 
             document.activeElement.tagName === 'TEXTAREA' || 
             document.activeElement.contentEditable === 'true')) {
            return;
        }
        
        // Delete键：删除选中的元素
        if (event.key === "Delete") {
            if (this.selectedElement || this.selectedElements.length > 0) {
                event.preventDefault();
                this.deleteSelectedElement();
            }
            return;
        }
        
        // Ctrl+A：全选所有元素
        if ((event.ctrlKey || event.metaKey) && event.key === "a") {
            event.preventDefault();
            this.selectAllElements();
            return;
        }
        
        // Ctrl+C：复制选中的元素
        if ((event.ctrlKey || event.metaKey) && event.key === "c") {
            event.preventDefault();
            this.copySelectedElements();
            return;
        }
        
        // Ctrl+V：粘贴复制的元素
        if ((event.ctrlKey || event.metaKey) && event.key === "v") {
            event.preventDefault();
            this.pasteElements();
            return;
        }
        
        // Ctrl+Z：撤销
        if ((event.ctrlKey || event.metaKey) && event.key === "z") {
            event.preventDefault();
            this.undo();
            return;
        }
        
        // Ctrl+Y：重做
        if ((event.ctrlKey || event.metaKey) && event.key === "y") {
            event.preventDefault();
            this.redo();
            return;
        }
    }

    /**
     * 处理鼠标滚轮事件（缩放）
     * @param {WheelEvent} event - 滚轮事件
     */
    handleWheel(event) {
        event.preventDefault();
        
        var zoomChange = event.deltaY > 0 ? -this.zoomStep : this.zoomStep;
        var newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.zoomScale + zoomChange));
        
        if (newZoom !== this.zoomScale) {
            this.zoomScale = newZoom;
            this.updateCanvasSize();
            this.render();
        }
    }

    // ===================== 画布大小更新 =====================

    /**
     * 更新画布大小
     */
    updateCanvasSize() {
        if (this.backgroundImage) {
            var dimensions = {width: this.backgroundImage.width, height: this.backgroundImage.height};
            var maxWidth = window.innerWidth - 100;
            var maxHeight = window.innerHeight - 300;
            
            let canvasWidth = dimensions.width;
            let canvasHeight = dimensions.height;
            
            // 如果图片太小，进行放大
            if (dimensions.width < 800 || dimensions.height < 600) {
                var scaleFactor = Math.max(800 / dimensions.width, 600 / dimensions.height);
                canvasWidth = dimensions.width * scaleFactor;
                canvasHeight = dimensions.height * scaleFactor;
            }
            
            // 如果图片太大，进行缩小
            if (canvasWidth > maxWidth || canvasHeight > maxHeight) {
                var scaleDown = Math.min(maxWidth / canvasWidth, maxHeight / canvasHeight);
                canvasWidth *= scaleDown;
                canvasHeight *= scaleDown;
            }
            
            var displayWidth = canvasWidth * this.zoomScale;
            var displayHeight = canvasHeight * this.zoomScale;
            
            this.canvas.style.width = displayWidth + "px";
            this.canvas.style.height = displayHeight + "px";
            this.displayScale = canvasWidth / dimensions.width * this.zoomScale;
        }
    }

    // ===================== 选择工具处理 =====================

    /**
     * 处理选择工具的鼠标按下事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleSelectMouseDown(mousePos) {
        // 如果正在多选拖动中，处理多选拖动逻辑
        if (this.isDraggingMultiple) {
            return;
        }

        // 检查是否点击在已选中的元素上
        if (this.selectedElement) {
            var resizeHandle = this.getResizeHandle(mousePos.x, mousePos.y, this.selectedElement);
            
            if (resizeHandle) {
                // 开始缩放
                this.isResizing = true;
                this.resizeHandle = resizeHandle;
                this.resizeStartBounds = this.getElementBounds(this.selectedElement);
                this.resizeStartPos = {x: mousePos.x, y: mousePos.y};
                this.render();
                return;
            }
        }

        // 检查是否点击在多选元素上
        if (this.selectedElements.length > 0) {
            for (let element of this.selectedElements) {
                if (this.isPointInElement(mousePos.x, mousePos.y, element)) {
                    // 开始多选拖动
                    this.isDraggingMultiple = true;
                    this.dragOffset = {x: mousePos.x - this.startX, y: mousePos.y - this.startY};
                    this.render();
                    return;
                }
            }
        }
        
        // 选择元素
        var element = this.getElementAtPoint(mousePos.x, mousePos.y);
        
        if (element) {
            // 如果点击的是当前已选中的元素，开始拖动
            if (this.selectedElement === element) {
                this.isDragging = true;
                // 箭头元素没有 x, y 属性，需要特殊处理
                if (element.type === "arrow") {
                    // 使用箭头的中点来计算拖动偏移
                    const centerX = (element.startX + element.endX) / 2;
                    const centerY = (element.startY + element.endY) / 2;
                    this.dragOffset = {x: mousePos.x - centerX, y: mousePos.y - centerY};
                } else {
                    this.dragOffset = {x: mousePos.x - element.x, y: mousePos.y - element.y};
                }
            } else {
                // 选择新元素，清除多选
                this.selectedElement = element;
                this.selectedElements = []; // 清除多选
                this.isDragging = true;
                // 箭头元素没有 x, y 属性，需要特殊处理
                if (element.type === "arrow") {
                    // 使用箭头的中点来计算拖动偏移
                    const centerX = (element.startX + element.endX) / 2;
                    const centerY = (element.startY + element.endY) / 2;
                    this.dragOffset = {x: mousePos.x - centerX, y: mousePos.y - centerY};
                } else {
                    this.dragOffset = {x: mousePos.x - element.x, y: mousePos.y - element.y};
                }
            }
            this.showPropertyPanel(element);
        } else {
            // 点击空白处，开始矩形选择
            this.startRectangularSelection(mousePos);
            this.selectedElement = null;
            this.selectedElements = [];
            this.hidePropertyPanel();
            // 更新工具选项显示（显示select选项）
            this.updateToolOptionsForSelection();
        }
        
        this.render();
    }

    /**
     * 处理选择工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleSelectMouseMove(mousePos) {
        if (this.isResizing && this.selectedElement && this.resizeHandle) {
            this.resizeElement(mousePos);
            this.render();
            // 实时更新属性面板
            this.updatePropertyPanelValues();
        } else if (this.isDraggingMultiple) {
            // 处理多选拖动
            this.handleMultipleSelectionMove(mousePos);
        } else if (this.isDragging && this.selectedElement) {
            // 处理单选拖动
            const newX = mousePos.x - this.dragOffset.x;
            const newY = mousePos.y - this.dragOffset.y;
            
            if (this.selectedElement.type === "brush") {
                // 画笔元素需要移动所有点
                const deltaX = newX - this.selectedElement.x;
                const deltaY = newY - this.selectedElement.y;
                
                this.selectedElement.x = newX;
                this.selectedElement.y = newY;
                
                if (this.selectedElement.points) {
                    this.selectedElement.points = this.selectedElement.points.map(point => ({
                        x: point.x + deltaX,
                        y: point.y + deltaY
                    }));
                }
            } else if (this.selectedElement.type === "arrow") {
                // 箭头元素需要移动起始点和结束点
                // 计算箭头的当前中心点
                const currentCenterX = (this.selectedElement.startX + this.selectedElement.endX) / 2;
                const currentCenterY = (this.selectedElement.startY + this.selectedElement.endY) / 2;
                
                // 计算从当前中心到新位置的距离
                const deltaX = newX - currentCenterX;
                const deltaY = newY - currentCenterY;
                
                // 确保坐标有效
                if (this.areFiniteValues([deltaX, deltaY])) {
                    this.selectedElement.startX += deltaX;
                    this.selectedElement.startY += deltaY;
                    this.selectedElement.endX += deltaX;
                    this.selectedElement.endY += deltaY;
                }
            } else {
                // 其他元素只移动位置
                this.selectedElement.x = newX;
                this.selectedElement.y = newY;
            }
            
            this.render();
            // 实时更新属性面板
            this.updatePropertyPanelValues();
        } else if (this.isMultiSelecting) {
            // 正在矩形选择中，更新选择框
            this.updateRectangularSelection(mousePos);
        } else if (this.selectedElement || this.selectedElements.length > 0) {
            var resizeHandle = this.getResizeHandle(mousePos.x, mousePos.y, this.selectedElement);
            this.updateCursor(resizeHandle);
        }
    }

    /**
     * 处理选择工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleSelectMouseUp(mousePos) {
        if (this.isMultiSelecting) {
            // 完成矩形选择
            this.finishRectangularSelection(mousePos);
        } else if (this.isDraggingMultiple) {
            // 结束多选拖动，保存状态
            this.saveState();
        } else if (this.isDragging || this.isResizing) {
            // 单选拖动或缩放结束，保存状态
            this.saveState();
        }
        
        this.isDragging = false;
        this.isDraggingMultiple = false;
        this.isResizing = false;
        this.resizeHandle = null;
        this.canvas.style.cursor = "default";
    }

    // ===================== 裁剪工具处理 =====================

    /**
     * 处理裁剪工具的鼠标按下事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleCropMouseDown(mousePos) {
        this.cropArea = {x: mousePos.x, y: mousePos.y, width: 0, height: 0};
        this.isCropping = true;
    }

    /**
     * 处理裁剪工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleCropMouseMove(mousePos) {
        if (this.isCropping && this.cropArea) {
            this.cropArea.width = mousePos.x - this.cropArea.x;
            this.cropArea.height = mousePos.y - this.cropArea.y;
            this.render();
        }
    }

    /**
     * 处理裁剪工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleCropMouseUp(mousePos) {
        if (this.isCropping && this.cropArea) {
            if (Math.abs(this.cropArea.width) > 10 && Math.abs(this.cropArea.height) > 10) {
                this.showCropConfirmation();
            } else {
                this.cropArea = null;
                this.render();
            }
        }
        
        this.isCropping = false;
    }

    /**
     * 应用裁剪
     */
    applyCrop() {
        if (this.cropArea) {
            // 计算裁剪区域的边界
            let cropX = Math.max(0, Math.min(this.cropArea.x, this.cropArea.x + this.cropArea.width));
            let cropY = Math.max(0, Math.min(this.cropArea.y, this.cropArea.y + this.cropArea.height));
            let cropWidth = Math.abs(this.cropArea.width);
            let cropHeight = Math.abs(this.cropArea.height);
            
            // 创建新的画布用于裁剪
            var cropCanvas = document.createElement("canvas");
            var cropCtx = cropCanvas.getContext("2d");
            cropCanvas.width = cropWidth;
            cropCanvas.height = cropHeight;
            
            if (this.backgroundImage) {
                cropCtx.drawImage(this.backgroundImage, cropX, cropY, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight);
            }
            
            // 加载裁剪后的图片
            let croppedImage = new Image;
            croppedImage.onload = () => {
                this.backgroundImage = croppedImage;
                this.canvas.width = cropWidth;
                this.canvas.height = cropHeight;
                
                // 调整画布显示大小
                var maxWidth = window.innerWidth - 100;
                var maxHeight = window.innerHeight - 300;
                var scale = Math.min(maxWidth / cropWidth, maxHeight / cropHeight, 1);
                
                if (scale < 1) {
                    this.canvas.style.width = cropWidth * scale + "px";
                    this.canvas.style.height = cropHeight * scale + "px";
                } else {
                    this.canvas.style.width = cropWidth + "px";
                    this.canvas.style.height = cropHeight + "px";
                }
                
                this.displayScale = scale < 1 ? scale : 1;
                
                // 调整所有元素的位置
                this.elements.forEach(element => {
                    element.x -= cropX;
                    element.y -= cropY;
                });
                
                // 移除超出裁剪区域的元素
                this.elements = this.elements.filter(element => 
                    element.x >= 0 && element.y >= 0 && element.x < cropWidth && element.y < cropHeight
                );
                
                this.cropArea = null;
                this.saveState();
                this.render();
            };
            croppedImage.src = cropCanvas.toDataURL();
        }
    }

    /**
     * 显示裁剪确认对话框
     */
    showCropConfirmation() {
        var container = document.createElement("div");
        container.id = "cropConfirmContainer";
        container.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 1000;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 15px;
        `;
        
        var message = document.createElement("div");
        message.textContent = "确定要裁剪到选中区域吗？";
        message.style.cssText = "font-size: 16px; color: #333; margin-bottom: 10px;";
        
        var buttonContainer = document.createElement("div");
        buttonContainer.style.cssText = "display: flex; gap: 10px;";
        
        var confirmBtn = document.createElement("button");
        confirmBtn.textContent = "确定裁剪";
        confirmBtn.style.cssText = `
            padding: 8px 16px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        `;
        
        var cancelBtn = document.createElement("button");
        cancelBtn.textContent = "取消";
        cancelBtn.style.cssText = `
            padding: 8px 16px;
            background: #6c757d;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        `;
        
        confirmBtn.onclick = () => {
            this.applyCrop();
            this.setTool("select");
            this.hideCropConfirmation();
        };
        
        cancelBtn.onclick = () => {
            this.cropArea = null;
            this.render();
            this.hideCropConfirmation();
        };
        
        buttonContainer.appendChild(confirmBtn);
        buttonContainer.appendChild(cancelBtn);
        container.appendChild(message);
        container.appendChild(buttonContainer);
        document.body.appendChild(container);
    }

    /**
     * 隐藏裁剪确认对话框
     */
    hideCropConfirmation() {
        var container = document.getElementById("cropConfirmContainer");
        if (container) {
            container.remove();
        }
    }

    // ===================== 画笔工具处理 =====================

    /**
     * 处理画笔工具的鼠标按下事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleBrushMouseDown(mousePos) {
        // 首先检查是否点击在现有的画笔元素上
        const existingElement = this.getElementAtPoint(mousePos.x, mousePos.y);
        if (existingElement && existingElement.type === "brush") {
            // 如果点击在现有画笔上，开始拖动
            this.selectedElement = existingElement;
            this.isDragging = true;
            this.dragOffset = {x: mousePos.x - existingElement.x, y: mousePos.y - existingElement.y};
            this.showPropertyPanel(existingElement);
            return;
        }
        
        // 如果没有点击在现有画笔上，创建新的画笔描边
        this.currentStroke = {
            type: "brush",
            points: [{x: mousePos.x, y: mousePos.y}],
            color: this.settings.brush.color,
            size: this.settings.brush.size,
            // 为画笔元素添加位置属性，用于拖动
            x: mousePos.x,
            y: mousePos.y
        };
    }

    /**
     * 处理画笔工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleBrushMouseMove(mousePos) {
        if (this.isDragging && this.selectedElement && this.selectedElement.type === "brush") {
            // 拖动现有画笔元素时，更新所有点的位置
            const deltaX = mousePos.x - this.dragOffset.x - this.selectedElement.x;
            const deltaY = mousePos.y - this.dragOffset.y - this.selectedElement.y;
            
            this.selectedElement.x = mousePos.x - this.dragOffset.x;
            this.selectedElement.y = mousePos.y - this.dragOffset.y;
            
            // 更新所有点的位置
            if (this.selectedElement.points) {
                this.selectedElement.points = this.selectedElement.points.map(point => ({
                    x: point.x + deltaX,
                    y: point.y + deltaY
                }));
            }
            
            this.render();
            this.updatePropertyPanelValues();
        } else if (this.currentStroke) {
            // 绘制新的画笔描边
            this.currentStroke.points.push({x: mousePos.x, y: mousePos.y});
            this.render();
        }
    }

    /**
     * 处理画笔工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleBrushMouseUp(mousePos) {
        if (this.isDragging && this.selectedElement && this.selectedElement.type === "brush") {
            // 结束拖动操作
            this.isDragging = false;
            this.saveState();
        } else if (this.currentStroke) {
            // 结束新的画笔描边
            this.elements.push(this.currentStroke);
            this.selectedElement = this.currentStroke;
            this.showPropertyPanel(this.currentStroke);
            this.currentStroke = null;
            this.saveState();
        }
    }

    // ===================== 形状工具处理 =====================

    /**
     * 处理形状工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleShapeMouseMove(mousePos) {
        this.render();
        if (this.currentTool === "arrow") {
            this.drawArrowPreview(this.startX, this.startY, mousePos.x, mousePos.y);
        } else {
            this.drawShapePreview(this.startX, this.startY, mousePos.x, mousePos.y);
        }
    }

    /**
     * 处理形状工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleShapeMouseUp(mousePos) {
        if (this.currentTool === "arrow") {
            // 处理箭头工具
            this.handleArrowMouseUp(mousePos);
            return;
        }
        
        var width = mousePos.x - this.startX;
        var height = mousePos.y - this.startY;
        
        if (Math.abs(width) > 5 && Math.abs(height) > 5) {
            var shapeType = this.currentTool === "ellipse" ? "ellipse" : "rect";
            var settings = this.currentTool === "ellipse" ? this.settings.ellipse : this.settings.rectangle;
            
            var element = {
                type: "shape",
                shapeType: shapeType,
                x: this.startX,
                y: this.startY,
                width: width,
                height: height,
                color: settings.color,
                stroke: settings.stroke
            };
            
            this.elements.push(element);
            this.selectedElement = element;
            this.showPropertyPanel(element);
            this.saveState();
        }
        
        this.render();
    }

    /**
     * 处理箭头工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleArrowMouseUp(mousePos) {
        var endX = this.ensureFiniteValue(mousePos.x);
        var endY = this.ensureFiniteValue(mousePos.y);
        var startX = this.ensureFiniteValue(this.startX);
        var startY = this.ensureFiniteValue(this.startY);
        
        // 计算距离，如果太短则不创建箭头
        var distance = Math.sqrt(Math.pow(endX - startX, 2) + Math.pow(endY - startY, 2));
        if (distance < 10) {
            return;
        }
        
        var settings = this.settings.arrow || { color: "#ff0000", stroke: 3 };
        
        // 确保所有值都是有效的
        const validStartX = this.ensureFiniteValue(startX);
        const validStartY = this.ensureFiniteValue(startY);
        const validEndX = this.ensureFiniteValue(endX);
        const validEndY = this.ensureFiniteValue(endY);
        const validStroke = this.ensureFiniteValue(settings.stroke, 3);
        const validColor = settings.color || "#ff0000";
        
        // 验证坐标有效性
        if (!this.areFiniteValues([validStartX, validStartY, validEndX, validEndY])) {
            console.warn("Invalid arrow coordinates, not creating element");
            return;
        }
        
        var element = {
            type: "arrow",
            startX: validStartX,
            startY: validStartY,
            endX: validEndX,
            endY: validEndY,
            color: validColor,
            stroke: validStroke
        };
        
        this.elements.push(element);
        this.selectedElement = element;
        this.showPropertyPanel(element);
        this.saveState();
    }

    // ===================== 高亮工具处理 =====================

    /**
     * 处理高亮工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleHighlightMouseMove(mousePos) {
        this.render();
        this.drawHighlightPreview(this.startX, this.startY, mousePos.x, mousePos.y);
    }

    /**
     * 处理高亮工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleHighlightMouseUp(mousePos) {
        var width = mousePos.x - this.startX;
        var height = mousePos.y - this.startY;
        
        if (Math.abs(width) > 5 && Math.abs(height) > 5) {
            var element = {
                type: "highlight",
                x: this.startX,
                y: this.startY,
                width: width,
                height: height
            };
            
            this.elements.push(element);
            this.selectedElement = element;
            this.showPropertyPanel(element);
            this.saveState();
        }
        
        this.render();
    }

    // ===================== 马赛克工具处理 =====================

    /**
     * 处理马赛克工具的鼠标按下事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleMosaicMouseDown(mousePos) {
        this.currentMosaicStroke = {
            type: "mosaic",
            points: [{x: mousePos.x, y: mousePos.y}],
            size: this.settings.mosaic.size,
            intensity: this.settings.mosaic.intensity
        };
    }

    /**
     * 处理马赛克工具的鼠标移动事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleMosaicMouseMove(mousePos) {
        if (this.currentMosaicStroke) {
            this.currentMosaicStroke.points.push({x: mousePos.x, y: mousePos.y});
            this.render();
        }
    }

    /**
     * 处理马赛克工具的鼠标释放事件
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleMosaicMouseUp(mousePos) {
        if (this.currentMosaicStroke) {
            this.elements.push(this.currentMosaicStroke);
            this.currentMosaicStroke = null;
            this.saveState();
        }
    }

    // ===================== 添加元素 =====================

    /**
     * 添加文字元素
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     */
    addText(x, y) {
        var element = {
            type: "text",
            x: x,
            y: y,
            content: "文字",
            color: this.settings.text.color,
            size: this.settings.text.size,
            bold: this.settings.text.bold,
            italic: this.settings.text.italic,
            underline: this.settings.text.underline,
            width: 80
        };
        
        this.elements.push(element);
        this.selectedElement = element;
        this.showPropertyPanel(element);
        this.saveState();
        this.render();
    }

    /**
     * 添加序号元素
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     */
    addNumber(x, y) {
        var element = {
            type: "number",
            x: x,
            y: y,
            number: this.numberCounter,
            color: "#007bff",
            size: 24
        };
        
        this.elements.push(element);
        this.selectedElement = element;
        this.showPropertyPanel(element);
        this.saveState();
        this.render();
        
        // 自动递增序号
        this.numberCounter++;
        if (this.numberCounter <= 10) {
            var nextButton = document.querySelector(`[data-number="${this.numberCounter}"]`);
            if (nextButton) {
                document.querySelectorAll(".number-button").forEach(btn => btn.classList.remove("active"));
                nextButton.classList.add("active");
            }
        }
    }

    /**
     * 编辑文字元素
     * @param {Object} textElement - 文字元素
     */
    editTextElement(textElement) {
        let overlay = document.createElement("div");
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10000;
        `;
        
        var dialog = document.createElement("div");
        dialog.style.cssText = `
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            min-width: 300px;
        `;
        
        var title = document.createElement("h3");
        title.textContent = "编辑文字";
        title.style.cssText = "margin: 0 0 15px 0; color: #333;";
        
        let textarea = document.createElement("textarea");
        textarea.value = textElement.content;
        textarea.style.cssText = `
            width: 100%;
            height: 120px;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 8px;
            font-family: Arial, sans-serif;
            font-size: 14px;
            resize: vertical;
            outline: none;
        `;
        
        var buttonContainer = document.createElement("div");
        buttonContainer.style.cssText = "margin-top: 15px; text-align: right;";
        
        var cancelBtn = document.createElement("button");
        cancelBtn.textContent = "取消";
        cancelBtn.style.cssText = `
            margin-right: 10px;
            padding: 8px 16px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 4px;
            cursor: pointer;
        `;
        
        var confirmBtn = document.createElement("button");
        confirmBtn.textContent = "确定";
        confirmBtn.style.cssText = `
            padding: 8px 16px;
            border: none;
            background: #007bff;
            color: white;
            border-radius: 4px;
            cursor: pointer;
        `;
        
        let closeDialog = () => {
            document.body.removeChild(overlay);
        };
        
        cancelBtn.onclick = closeDialog;
        confirmBtn.onclick = () => {
            var newContent = textarea.value;
            if (newContent.trim() !== "") {
                textElement.content = newContent;
                this.saveState();
                this.render();
            }
            closeDialog();
        };
        
        overlay.onkeydown = (event) => {
            if (event.key === "Escape") {
                closeDialog();
            }
        };
        
        buttonContainer.appendChild(cancelBtn);
        buttonContainer.appendChild(confirmBtn);
        dialog.appendChild(title);
        dialog.appendChild(textarea);
        dialog.appendChild(buttonContainer);
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        
        textarea.focus();
        textarea.select();
    }

    // ===================== 元素检测和处理 =====================

    /**
     * 获取指定位置的元素
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @returns {Object|null} 元素对象或null
     */
    getElementAtPoint(x, y) {
        for (let i = this.elements.length - 1; i >= 0; i--) {
            var element = this.elements[i];
            if (this.isPointInElement(x, y, element)) {
                return element;
            }
        }
        return null;
    }

    /**
     * 计算点到线段的距离
     * @param {number} px - 点的X坐标
     * @param {number} py - 点的Y坐标
     * @param {number} x1 - 线段起点的X坐标
     * @param {number} y1 - 线段起点的Y坐标
     * @param {number} x2 - 线段终点的X坐标
     * @param {number} y2 - 线段终点的Y坐标
     * @returns {number} 点到线段的距离
     */
    pointToLineSegmentDistance(px, py, x1, y1, x2, y2) {
        // 计算向量
        const A = px - x1;
        const B = py - y1;
        const C = x2 - x1;
        const D = y2 - y1;
        
        // 计算点积
        const dot = A * C + B * D;
        // 计算线段长度的平方
        const len_sq = C * C + D * D;
        
        // 如果线段长度为0，返回点到起点的距离
        if (len_sq === 0) {
            return Math.sqrt(A * A + B * B);
        }
        
        // 计算参数t
        const param = dot / len_sq;
        
        // 找到投影点
        let xx, yy;
        if (param < 0) {
            // 投影点在线段起点之前
            xx = x1;
            yy = y1;
        } else if (param > 1) {
            // 投影点在线段终点之后
            xx = x2;
            yy = y2;
        } else {
            // 投影点在线段上
            xx = x1 + param * C;
            yy = y1 + param * D;
        }
        
        // 计算点到投影点的距离
        const dx = px - xx;
        const dy = py - yy;
        return Math.sqrt(dx * dx + dy * dy);
    }

    /**
     * 验证箭头元素的有效性
     * @param {Object} arrowElement - 箭头元素
     * @returns {boolean} 是否有效
     */
    isValidArrowElement(arrowElement) {
        if (!arrowElement || typeof arrowElement !== 'object') {
            return false;
        }
        
        // 检查必要的属性是否存在
        const requiredProperties = ['startX', 'startY', 'endX', 'endY', 'color', 'stroke'];
        for (const prop of requiredProperties) {
            if (!(prop in arrowElement)) {
                return false;
            }
        }
        
        // 检查数值属性
        const numericProperties = ['startX', 'startY', 'endX', 'endY', 'stroke'];
        for (const prop of numericProperties) {
            if (typeof arrowElement[prop] !== 'number' || 
                isNaN(arrowElement[prop]) || 
                !isFinite(arrowElement[prop])) {
                return false;
            }
        }
        
        // 检查颜色属性
        if (typeof arrowElement.color !== 'string' || !arrowElement.color) {
            return false;
        }
        
        return true;
    }

    /**
     * 确保数值是有限的，如果不是则返回默认值
     * @param {number} value - 要检查的数值
     * @param {number} defaultValue - 默认值，默认为 0
     * @returns {number} 有限数值或默认值
     */
    ensureFiniteValue(value, defaultValue = 0) {
        if (typeof value === 'number' && isFinite(value)) {
            return value;
        }
        return defaultValue;
    }

    /**
     * 检查多个值是否都是有限的
     * @param {Array} values - 数值数组
     * @returns {boolean} 是否所有值都有限
     */
    areFiniteValues(values) {
        if (!Array.isArray(values)) {
            return false;
        }
        return values.every(value => 
            typeof value === 'number' && isFinite(value)
        );
    }

    /**
     * 检测点是否在元素内
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {Object} element - 元素对象
     * @returns {boolean} 是否在元素内
     */
    isPointInElement(x, y, element) {
        // 使用统一的边界框检测（简化版）
        const bounds = this.getElementBounds(element);
        
        // 简单矩形边界检测
        return x >= bounds.x && 
               x <= bounds.x + bounds.width && 
               y >= bounds.y && 
               y <= bounds.y + bounds.height;
    }

    // ===================== 渲染 =====================

    /**
     * 切换网格显示
     */
    toggleGrid() {
        this.showGrid = !this.showGrid;
        
        // 更新网格按钮的活跃状态
        var gridButton = document.querySelector('[data-tool="grid"]');
        if (gridButton) {
            if (this.showGrid) {
                gridButton.classList.add('active');
            } else {
                gridButton.classList.remove('active');
            }
        }
        
        this.render();
    }

    /**
     * 绘制网格坐标系
     */
    drawGrid() {
        if (!this.showGrid) return;
        
        var ctx = this.ctx;
        var gridSize = this.gridSize;
        var canvasWidth = this.canvas.width;
        var canvasHeight = this.canvas.height;
        
        // 保存当前上下文状态
        ctx.save();
        
        // 设置网格线样式
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)';
        ctx.lineWidth = 1;
        
        // 绘制垂直网格线
        for (var x = 0; x <= canvasWidth; x += gridSize) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvasHeight);
            ctx.stroke();
        }
        
        // 绘制水平网格线
        for (var y = 0; y <= canvasHeight; y += gridSize) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvasWidth, y);
            ctx.stroke();
        }
        
        // 绘制坐标轴（粗一些）
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
        ctx.lineWidth = 2;
        
        // X轴（顶部边框）
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(canvasWidth, 0);
        ctx.stroke();
        
        // Y轴（左边框）
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, canvasHeight);
        ctx.stroke();
        
        // 绘制坐标标签
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.font = '12px Arial';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        
        // X坐标标签（顶部）
        for (var x = 0; x <= canvasWidth; x += gridSize) {
            if (x > 0) { // 跳过0，0点的重复
                ctx.fillText(x + '', x + 2, 2);
            }
        }
        
        // Y坐标标签（左侧）
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        for (var y = 0; y <= canvasHeight; y += gridSize) {
            if (y > 0) { // 跳过0，0点的重复
                ctx.fillText(y + '', 2, y + gridSize/2);
            }
        }
        
        // 显示画布尺寸信息
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
        ctx.font = 'bold 14px Arial';
        ctx.fillText(canvasWidth + ' × ' + canvasHeight, canvasWidth - 10, canvasHeight - 10);
        
        // 恢复上下文状态
        ctx.restore();
    }

    /**
     * 渲染画布
     */
    render() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 绘制背景图片
        if (this.backgroundImage) {
            this.ctx.drawImage(this.backgroundImage, 0, 0, this.canvas.width, this.canvas.height);
        }
        
        // 绘制高亮遮罩
        this.drawHighlightMask();
        
        // 绘制元素
        this.elements.forEach(element => {
            if (element.type !== "highlight" && element.type !== "number") {
                this.drawElement(element);
            }
        });
        
        // 绘制当前笔画
        if (this.currentStroke) {
            this.drawBrushStroke(this.currentStroke);
        }
        
        if (this.currentMosaicStroke) {
            this.drawMosaicStroke(this.currentMosaicStroke);
        }
        
        // 绘制序号（在最上层）
        this.elements.forEach(element => {
            if (element.type === "number") {
                this.drawElement(element);
            }
        });
        
        // 绘制选择边框
        if (this.selectedElement && this.currentTool === "select") {
            this.drawSelectionBorder(this.selectedElement);
        }
        
        // 绘制多选边框
        if (this.selectedElements.length > 0 && this.currentTool === "select") {
            this.drawMultipleSelectionBorder();
        }
        
        // 绘制矩形选择框
        if (this.selectionBox && this.isMultiSelecting) {
            this.drawSelectionBox(this.selectionBox);
        }
        
        // 绘制裁剪区域
        if (this.cropArea) {
            this.drawCropArea();
        }
        
        // 绘制网格坐标系
        this.drawGrid();
    }

    /**
     * 绘制单个元素
     * @param {Object} element - 元素对象
     */
    drawElement(element) {
        this.ctx.save();
        
        switch(element.type) {
            case "text":
                this.drawText(element);
                break;
            case "number":
                this.drawNumber(element);
                break;
            case "shape":
                this.drawShape(element);
                break;
            case "arrow":
                this.drawArrow(element);
                break;
            case "highlight":
                this.drawHighlight(element);
                break;
            case "brush":
                this.drawBrushStroke(element);
                break;
            case "mosaic":
                this.drawMosaicStroke(element);
                break;
        }
        
        this.ctx.restore();
    }

    /**
     * 绘制文字
     * @param {Object} textElement - 文字元素
     */
    drawText(textElement) {
        this.ctx.fillStyle = textElement.color;
        
        let fontWeight = "";
        if (textElement.bold) {
            fontWeight += "bold ";
        }
        if (textElement.italic) {
            fontWeight += "italic ";
        }
        
        let font = fontWeight + textElement.size + "px Arial";
        this.ctx.font = font;
        
        let lineHeight = 1.2 * textElement.size;
        let lines = textElement.content.split("\n");
        
        lines.forEach((line, index) => {
            let y = textElement.y + index * lineHeight;
            this.ctx.fillText(line, textElement.x, y);
            
            if (textElement.underline && line !== "") {
                let textWidth = this.ctx.measureText(line).width;
                this.ctx.beginPath();
                this.ctx.moveTo(textElement.x, y + 2);
                this.ctx.lineTo(textElement.x + textWidth, y + 2);
                this.ctx.strokeStyle = textElement.color;
                this.ctx.lineWidth = 1;
                this.ctx.stroke();
            }
        });
    }

    /**
     * 绘制序号
     * @param {Object} numberElement - 序号元素
     */
    drawNumber(numberElement) {
        var radius = numberElement.size;
        
        this.ctx.fillStyle = numberElement.color;
        this.ctx.beginPath();
        this.ctx.arc(numberElement.x, numberElement.y, radius, 0, 2 * Math.PI);
        this.ctx.fill();
        
        this.ctx.fillStyle = "white";
        this.ctx.font = "bold " + (1.2 * radius) + "px Arial";
        this.ctx.textAlign = "center";
        this.ctx.textBaseline = "middle";
        this.ctx.fillText(numberElement.number.toString(), numberElement.x, numberElement.y);
        
        // 重置文本对齐
        this.ctx.textAlign = "start";
        this.ctx.textBaseline = "alphabetic";
    }

    /**
     * 绘制形状
     * @param {Object} shapeElement - 形状元素
     */
    drawShape(shapeElement) {
        this.ctx.strokeStyle = shapeElement.color;
        this.ctx.lineWidth = shapeElement.stroke;
        this.ctx.beginPath();
        
        if (shapeElement.shapeType === "ellipse") {
            var centerX = shapeElement.x + shapeElement.width / 2;
            var centerY = shapeElement.y + shapeElement.height / 2;
            var radiusX = Math.abs(shapeElement.width) / 2;
            var radiusY = Math.abs(shapeElement.height) / 2;
            this.ctx.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, 2 * Math.PI);
        } else {
            var x = Math.min(shapeElement.x, shapeElement.x + shapeElement.width);
            var y = Math.min(shapeElement.y, shapeElement.y + shapeElement.height);
            var width = Math.abs(shapeElement.width);
            var height = Math.abs(shapeElement.height);
            this.ctx.roundRect(x, y, width, height, 10);
        }
        
        this.ctx.stroke();
    }

    /**
     * 绘制箭头
     * @param {Object} arrowElement - 箭头元素
     */
    drawArrow(arrowElement) {
        // 验证箭头元素数据的有效性
        if (!this.isValidArrowElement(arrowElement)) {
            console.warn("Invalid arrow element data:", arrowElement);
            return;
        }
        
        // 确保坐标是有限数值
        const startX = this.ensureFiniteValue(arrowElement.startX);
        const startY = this.ensureFiniteValue(arrowElement.startY);
        const endX = this.ensureFiniteValue(arrowElement.endX);
        const endY = this.ensureFiniteValue(arrowElement.endY);
        const color = arrowElement.color || "#ff0000";
        const stroke = this.ensureFiniteValue(arrowElement.stroke || 3);
        
        // 如果坐标无效，则返回
        if (!this.areFiniteValues([startX, startY, endX, endY])) {
            console.warn("Invalid arrow coordinates:", {startX, startY, endX, endY});
            return;
        }
        
        // 创建从箭尾到箭头的渐变线条（从细到粗）
        const gradient = this.ctx.createLinearGradient(startX, startY, endX, endY);
        gradient.addColorStop(0, color);
        gradient.addColorStop(0.3, color);
        gradient.addColorStop(1, color);
        
        this.ctx.strokeStyle = gradient;
        this.ctx.lineCap = "round";
        this.ctx.lineJoin = "round";
        
        // 绘制主线条的渐变效果（从细到粗）
        const steps = 20; // 分段数量，数值越大越平滑
        for (let i = 0; i < steps; i++) {
            const t1 = i / steps;
            const t2 = (i + 1) / steps;
            
            const startProgress = t1;
            const endProgress = t2;
            
            // 计算当前段的起点和终点
            const segmentStartX = startX + (endX - startX) * startProgress;
            const segmentStartY = startY + (endY - startY) * startProgress;
            const segmentEndX = startX + (endX - startX) * endProgress;
            const segmentEndY = startY + (endY - startY) * endProgress;
            
            // 线条宽度从细到粗
            const segmentWidth = stroke * (0.3 + 0.7 * endProgress);
            this.ctx.lineWidth = segmentWidth;
            
            this.ctx.beginPath();
            this.ctx.moveTo(segmentStartX, segmentStartY);
            this.ctx.lineTo(segmentEndX, segmentEndY);
            this.ctx.stroke();
        }
        
        // 绘制箭头头部
        const angle = Math.atan2(endY - startY, endX - startX);
        const arrowLength = 15 + stroke * 2; // 根据线宽调整箭头长度
        const arrowAngle = Math.PI / 6; // 箭头角度 (30度)
        
        // 箭头的两个点
        const arrowPoint1X = endX - arrowLength * Math.cos(angle - arrowAngle);
        const arrowPoint1Y = endY - arrowLength * Math.sin(angle - arrowAngle);
        const arrowPoint2X = endX - arrowLength * Math.cos(angle + arrowAngle);
        const arrowPoint2Y = endY - arrowLength * Math.sin(angle + arrowAngle);
        
        // 绘制箭头头部（更粗一些）
        this.ctx.lineWidth = (arrowElement.stroke || 3) * 1.5;
        this.ctx.beginPath();
        this.ctx.moveTo(arrowElement.endX, arrowElement.endY);
        this.ctx.lineTo(arrowPoint1X, arrowPoint1Y);
        this.ctx.moveTo(arrowElement.endX, arrowElement.endY);
        this.ctx.lineTo(arrowPoint2X, arrowPoint2Y);
        this.ctx.stroke();
    }

    /**
     * 绘制马赛克笔画
     * @param {Object} mosaicElement - 马赛克元素
     */
    drawMosaicStroke(mosaicElement) {
        if (mosaicElement.points && mosaicElement.points.length !== 0) {
            let size = mosaicElement.size;
            let intensity = mosaicElement.intensity;
            
            mosaicElement.points.forEach(point => {
                this.applyMosaicAtPoint(point.x, point.y, size, intensity);
            });
        }
    }

    /**
     * 在指定点应用马赛克效果
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {number} size - 马赛克大小
     * @param {number} intensity - 马赛克强度
     */
    applyMosaicAtPoint(x, y, size, intensity) {
        var imageData = this.ctx.getImageData(x - size/2, y - size/2, size, size);
        var data = imageData.data;
        
        for (let i = 0; i < data.length; i += 4) {
            var pixelIndex = Math.floor(i / 4);
            var blockX = Math.floor(pixelIndex % size / intensity) * intensity;
            var blockIndex = 4 * (Math.floor(Math.floor(pixelIndex / size) / intensity) * intensity * size + blockX);
            
            if (blockIndex < data.length) {
                data[i] = data[blockIndex];
                data[i + 1] = data[blockIndex + 1];
                data[i + 2] = data[blockIndex + 2];
            }
        }
        
        this.ctx.putImageData(imageData, x - size/2, y - size/2);
    }

    /**
     * 绘制高亮
     * @param {Object} highlightElement - 高亮元素
     */
    drawHighlight(highlightElement) {
        if (this.selectedElement === highlightElement) {
            this.drawSelectionBorder(highlightElement);
        }
    }

    /**
     * 绘制高亮遮罩
     */
    drawHighlightMask() {
        if (this.elements.filter(element => element.type === "highlight").length !== 0) {
            var maskCanvas = document.createElement("canvas");
            maskCanvas.width = this.canvas.width;
            maskCanvas.height = this.canvas.height;
            
            let maskCtx = maskCanvas.getContext("2d");
            
            // 绘制半透明黑色遮罩
            maskCtx.fillStyle = "rgba(0, 0, 0, 0.5)";
            maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
            
            // 清除高亮区域
            maskCtx.globalCompositeOperation = "destination-out";
            this.elements.forEach(element => {
                if (element.type === "highlight") {
                    maskCtx.fillStyle = "rgba(255, 255, 255, 1)";
                    this.drawRoundedRect(maskCtx, element.x, element.y, element.width, element.height, 8);
                    maskCtx.fill();
                }
            });
            
            // 将遮罩绘制到主画布
            this.ctx.drawImage(maskCanvas, 0, 0);
        }
    }

    /**
     * 绘制圆角矩形
     * @param {CanvasRenderingContext2D} ctx - 画布上下文
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {number} width - 宽度
     * @param {number} height - 高度
     * @param {number} radius - 圆角半径
     */
    drawRoundedRect(ctx, x, y, width, height, radius) {
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
    }

    /**
     * 绘制画笔笔画
     * @param {Object} brushElement - 画笔元素
     */
    drawBrushStroke(brushElement) {
        if (brushElement.points && brushElement.points.length >= 2) {
            this.ctx.strokeStyle = brushElement.color;
            this.ctx.lineWidth = brushElement.size;
            this.ctx.lineCap = "round";
            this.ctx.lineJoin = "round";
            
            this.ctx.beginPath();
            this.ctx.moveTo(brushElement.points[0].x, brushElement.points[0].y);
            
            for (let i = 1; i < brushElement.points.length; i++) {
                this.ctx.lineTo(brushElement.points[i].x, brushElement.points[i].y);
            }
            
            this.ctx.stroke();
        }
    }

    /**
     * 绘制选择边框
     * @param {Object} element - 元素对象
     */
    drawSelectionBorder(element) {
        this.ctx.strokeStyle = "#007bff";
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);
        
        var bounds = this.getElementBounds(element);
        this.ctx.strokeRect(bounds.x - 5, bounds.y - 5, bounds.width + 10, bounds.height + 10);
        
        this.ctx.setLineDash([]);
        this.drawResizeHandles(bounds, element);
        
        // 在选择框上方显示坐标信息
        this.drawSelectionCoordinates(bounds);
    }

    /**
     * 绘制选择框坐标信息
     * @param {Object} bounds - 元素边界
     */
    drawSelectionCoordinates(bounds) {
        var ctx = this.ctx;
        
        // 计算坐标文本
        var x = Math.round(bounds.x);
        var y = Math.round(bounds.y);
        var width = Math.round(bounds.width);
        var height = Math.round(bounds.height);
        var coordsText = `(${x}, ${y}, ${width}, ${height})`;
        
        // 设置文本样式
        ctx.save();
        ctx.font = 'bold 14px Arial';
        ctx.textAlign = 'left';  // 左对齐
        ctx.textBaseline = 'bottom';  // 底部对齐
        
        // 计算文本背景位置（选择框左上角外侧）
        var padding = 8;
        var textX = bounds.x - padding - 10;  // 选择框左外侧
        var textY = bounds.y - padding - 10;  // 选择框上外侧
        
        // 计算文本尺寸
        var textWidth = ctx.measureText(coordsText).width;
        var bgX = textX - padding;
        var bgY = textY - 20;
        var bgWidth = textWidth + padding * 2;
        var bgHeight = 22;
        
        // 调整位置避免超出画布边界
        if (bgX < 5) {
            textX = bounds.x + bounds.width + padding + 5;  // 移到右侧外侧
            bgX = textX - padding;
        }
        if (bgY < 5) {
            textY = bounds.y + bounds.height + padding + 15;  // 移到下方外侧
            bgY = textY - 20;
        }
        
        // 绘制背景
        ctx.fillStyle = 'rgba(0, 123, 255, 0.9)';
        ctx.fillRect(bgX, bgY, bgWidth, bgHeight);
        
        // 绘制边框
        ctx.strokeStyle = 'rgba(0, 123, 255, 1)';
        ctx.lineWidth = 1;
        ctx.strokeRect(bgX, bgY, bgWidth, bgHeight);
        
        // 绘制文本
        ctx.fillStyle = 'white';
        ctx.fillText(coordsText, textX, textY);
        
        ctx.restore();
    }

    /**
     * 绘制缩放控制点
     * @param {Object} bounds - 元素边界
     * @param {Object} element - 元素对象
     */
    drawResizeHandles(bounds, element) {
        let handles = (element && (element.type === "text" || element.type === "number")) ? 
            [
                {x: bounds.x - 5, y: bounds.y - 5},
                {x: bounds.x + bounds.width + 5, y: bounds.y - 5},
                {x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height + 5},
                {x: bounds.x - 5, y: bounds.y + bounds.height + 5}
            ] : 
            [
                {x: bounds.x - 5, y: bounds.y - 5},
                {x: bounds.x + bounds.width / 2, y: bounds.y - 5},
                {x: bounds.x + bounds.width + 5, y: bounds.y - 5},
                {x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height / 2},
                {x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height + 5},
                {x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height + 5},
                {x: bounds.x - 5, y: bounds.y + bounds.height + 5},
                {x: bounds.x - 5, y: bounds.y + bounds.height / 2}
            ];
        
        this.ctx.fillStyle = "#007bff";
        this.ctx.strokeStyle = "#ffffff";
        this.ctx.lineWidth = 2;
        
        handles.forEach(handle => {
            this.ctx.fillRect(handle.x - 6, handle.y - 6, 12, 12);
            this.ctx.strokeRect(handle.x - 6, handle.y - 6, 12, 12);
        });
    }

    /**
     * 获取缩放控制点
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {Object} element - 元素对象
     * @returns {string|null} 控制点类型或null
     */
    getResizeHandle(x, y, element) {
        var bounds = this.getElementBounds(element);
        
        let handles = (element && (element.type === "text" || element.type === "number")) ? 
            [
                {type: "nw", x: bounds.x - 5, y: bounds.y - 5},
                {type: "ne", x: bounds.x + bounds.width + 5, y: bounds.y - 5},
                {type: "se", x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height + 5},
                {type: "sw", x: bounds.x - 5, y: bounds.y + bounds.height + 5}
            ] : 
            [
                {type: "nw", x: bounds.x - 5, y: bounds.y - 5},
                {type: "n", x: bounds.x + bounds.width / 2, y: bounds.y - 5},
                {type: "ne", x: bounds.x + bounds.width + 5, y: bounds.y - 5},
                {type: "e", x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height / 2},
                {type: "se", x: bounds.x + bounds.width + 5, y: bounds.y + bounds.height + 5},
                {type: "s", x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height + 5},
                {type: "sw", x: bounds.x - 5, y: bounds.y + bounds.height + 5},
                {type: "w", x: bounds.x - 5, y: bounds.y + bounds.height / 2}
            ];
        
        for (let handle of handles) {
            if (Math.abs(x - handle.x) <= 12 && Math.abs(y - handle.y) <= 12) {
                return handle.type;
            }
        }
        
        return null;
    }

    /**
     * 更新鼠标样式
     * @param {string|null} handleType - 控制点类型
     */
    updateCursor(handleType) {
        const cursorMap = {
            "nw": "nw-resize",
            "n": "n-resize",
            "ne": "ne-resize",
            "e": "e-resize",
            "se": "se-resize",
            "s": "s-resize",
            "sw": "sw-resize",
            "w": "w-resize"
        };
        
        this.canvas.style.cursor = handleType ? cursorMap[handleType] : "default";
    }

    /**
     * 缩放元素
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    resizeElement(mousePos) {
        if (this.selectedElement && this.resizeHandle) {
            var deltaX = mousePos.x - this.resizeStartPos.x;
            var deltaY = mousePos.y - this.resizeStartPos.y;
            var startBounds = this.resizeStartBounds;
            
            switch(this.selectedElement.type) {
                case "text":
                    this.resizeText(deltaX, deltaY, startBounds);
                    break;
                case "number":
                    this.resizeNumber(deltaX, deltaY, startBounds);
                    break;
                case "shape":
                case "highlight":
                    this.resizeShape(deltaX, deltaY, startBounds);
                    break;
                case "arrow":
                    this.resizeArrow(deltaX, deltaY, startBounds);
                    break;
            }
            
            // 实时更新属性面板
            this.updatePropertyPanelValues();
        }
    }

    /**
     * 缩放文字元素
     * @param {number} deltaX - X轴变化量
     * @param {number} deltaY - Y轴变化量
     * @param {Object} startBounds - 初始边界
     */
    resizeText(deltaX, deltaY, startBounds) {
        let sizeChange = 0;
        
        switch(this.resizeHandle) {
            case "nw":
                sizeChange = (-deltaX - deltaY) / 6;
                break;
            case "ne":
                sizeChange = (deltaX - deltaY) / 6;
                break;
            case "se":
                sizeChange = (deltaX + deltaY) / 6;
                break;
            case "sw":
                sizeChange = (-deltaX + deltaY) / 6;
                break;
        }
        
        this.selectedElement.size = Math.max(8, Math.min(150, this.selectedElement.size + sizeChange));
    }

    /**
     * 缩放序号元素
     * @param {number} deltaX - X轴变化量
     * @param {number} deltaY - Y轴变化量
     * @param {Object} startBounds - 初始边界
     */
    resizeNumber(deltaX, deltaY, startBounds) {
        var handle = this.resizeHandle;
        
        if (handle.includes("e") || handle.includes("w") || handle.includes("s") || handle.includes("n")) {
            var sizeChange = Math.max(deltaX, deltaY) / 2;
            this.selectedElement.size = Math.max(10, startBounds.width / 2 + sizeChange);
        }
    }

    /**
     * 缩放形状元素
     * @param {number} deltaX - X轴变化量
     * @param {number} deltaY - Y轴变化量
     * @param {Object} startBounds - 初始边界
     */
    resizeShape(deltaX, deltaY, startBounds) {
        var handle = this.resizeHandle;
        
        let newX = this.selectedElement.x;
        let newY = this.selectedElement.y;
        let newWidth = this.selectedElement.width;
        let newHeight = this.selectedElement.height;
        
        switch(handle) {
            case "nw":
                newX = startBounds.x + deltaX;
                newY = startBounds.y + deltaY;
                newWidth = startBounds.width - deltaX;
                newHeight = startBounds.height - deltaY;
                break;
            case "n":
                newY = startBounds.y + deltaY;
                newHeight = startBounds.height - deltaY;
                break;
            case "ne":
                newY = startBounds.y + deltaY;
                newWidth = startBounds.width + deltaX;
                newHeight = startBounds.height - deltaY;
                break;
            case "e":
                newWidth = startBounds.width + deltaX;
                break;
            case "se":
                newWidth = startBounds.width + deltaX;
                newHeight = startBounds.height + deltaY;
                break;
            case "s":
                newHeight = startBounds.height + deltaY;
                break;
            case "sw":
                newX = startBounds.x + deltaX;
                newWidth = startBounds.width - deltaX;
                newHeight = startBounds.height + deltaY;
                break;
            case "w":
                newX = startBounds.x + deltaX;
                newWidth = startBounds.width - deltaX;
                break;
        }
        
        // 确保最小尺寸
        if (Math.abs(newWidth) >= 10 && Math.abs(newHeight) >= 10) {
            this.selectedElement.x = newX;
            this.selectedElement.y = newY;
            this.selectedElement.width = newWidth;
            this.selectedElement.height = newHeight;
        }
    }

    /**
     * 缩放箭头元素
     * @param {number} deltaX - X轴变化量
     * @param {number} deltaY - Y轴变化量
     * @param {Object} startBounds - 初始边界
     */
    resizeArrow(deltaX, deltaY, startBounds) {
        var handle = this.resizeHandle;
        var element = this.selectedElement;
        
        // 初始坐标
        var origStartX = this.resizeStartElement.startX;
        var origStartY = this.resizeStartElement.startY;
        var origEndX = this.resizeStartElement.endX;
        var origEndY = this.resizeStartElement.endY;
        
        // 计算缩放比例
        var scaleX = 1;
        var scaleY = 1;
        var minSize = 10;
        
        switch(handle) {
            case "nw":  // 左上
                var newStartX = origStartX + deltaX;
                var newStartY = origStartY + deltaY;
                var newWidth = Math.abs(origEndX - newStartX);
                var newHeight = Math.abs(origEndY - newStartY);
                
                if (newWidth >= minSize && newHeight >= minSize) {
                    // 调整起始点
                    element.startX = newStartX;
                    element.startY = newStartY;
                }
                break;
                
            case "n":   // 上中
                var newStartY = origStartY + deltaY;
                var newHeight = Math.abs(origEndY - newStartY);
                
                if (newHeight >= minSize) {
                    element.startY = newStartY;
                }
                break;
                
            case "ne":  // 右上
                var newStartY = origStartY + deltaY;
                var newEndX = origEndX + deltaX;
                var newWidth = Math.abs(newEndX - origStartX);
                var newHeight = Math.abs(origEndY - newStartY);
                
                if (newWidth >= minSize && newHeight >= minSize) {
                    element.startY = newStartY;
                    element.endX = newEndX;
                }
                break;
                
            case "e":   // 右中
                var newEndX = origEndX + deltaX;
                var newWidth = Math.abs(newEndX - origStartX);
                
                if (newWidth >= minSize) {
                    element.endX = newEndX;
                }
                break;
                
            case "se":  // 右下
                var newEndX = origEndX + deltaX;
                var newEndY = origEndY + deltaY;
                var newWidth = Math.abs(newEndX - origStartX);
                var newHeight = Math.abs(newEndY - origStartY);
                
                if (newWidth >= minSize && newHeight >= minSize) {
                    element.endX = newEndX;
                    element.endY = newEndY;
                }
                break;
                
            case "s":   // 下中
                var newEndY = origEndY + deltaY;
                var newHeight = Math.abs(newEndY - origStartY);
                
                if (newHeight >= minSize) {
                    element.endY = newEndY;
                }
                break;
                
            case "sw":  // 左下
                var newStartX = origStartX + deltaX;
                var newEndY = origEndY + deltaY;
                var newWidth = Math.abs(origEndX - newStartX);
                var newHeight = Math.abs(newEndY - origStartY);
                
                if (newWidth >= minSize && newHeight >= minSize) {
                    element.startX = newStartX;
                    element.endY = newEndY;
                }
                break;
                
            case "w":   // 左中
                var newStartX = origStartX + deltaX;
                var newWidth = Math.abs(origEndX - newStartX);
                
                if (newWidth >= minSize) {
                    element.startX = newStartX;
                }
                break;
        }
    }

    /**
     * 获取元素边界
     * @param {Object} element - 元素对象
     * @returns {Object} 边界对象 {x, y, width, height}
     */
    getElementBounds(element) {
        switch(element.type) {
            case "text":
                var lineHeight = 1.2 * element.size;
                
                this.ctx.save();
                let font = "";
                if (element.bold) {
                    font += "bold ";
                }
                if (element.italic) {
                    font += "italic ";
                }
                font += element.size + "px Arial";
                this.ctx.font = font;
                
                var lines = element.content.split("\n");
                let maxWidth = 0;
                
                lines.forEach(line => {
                    let width = this.ctx.measureText(line).width;
                    maxWidth = Math.max(maxWidth, width);
                });
                
                maxWidth = Math.max(maxWidth, 20);
                this.ctx.restore();
                
                return {
                    x: element.x,
                    y: element.y - element.size,
                    width: maxWidth,
                    height: lines.length * lineHeight
                };
                
            case "number":
                var radius = element.size;
                return {
                    x: element.x - radius,
                    y: element.y - radius,
                    width: 2 * radius,
                    height: 2 * radius
                };
                
            case "shape":
            case "highlight":
                return {
                    x: Math.min(element.x, element.x + element.width),
                    y: Math.min(element.y, element.y + element.height),
                    width: Math.abs(element.width),
                    height: Math.abs(element.height)
                };
                
            case "arrow":
                // 计算箭头的边界框，确保所有坐标值都是有效数字
                const startX = this.ensureFiniteValue(element.startX, 0);
                const startY = this.ensureFiniteValue(element.startY, 0);
                const endX = this.ensureFiniteValue(element.endX, 0);
                const endY = this.ensureFiniteValue(element.endY, 0);
                
                const minX = Math.min(startX, endX);
                const maxX = Math.max(startX, endX);
                const minY = Math.min(startY, endY);
                const maxY = Math.max(startY, endY);
                
                // 考虑箭头头部和粗细
                const padding = (this.ensureFiniteValue(element.stroke, 3)) / 2 + 15; // 箭头头部大约15像素
                
                return {
                    x: minX - padding,
                    y: minY - padding,
                    width: (maxX - minX) + 2 * padding,
                    height: (maxY - minY) + 2 * padding
                };
                
            case "brush":
                if (element.points && element.points.length > 0) {
                    const minX = Math.min(...element.points.map(p => p.x));
                    const maxX = Math.max(...element.points.map(p => p.x));
                    const minY = Math.min(...element.points.map(p => p.y));
                    const maxY = Math.max(...element.points.map(p => p.y));
                    
                    // 考虑画笔宽度和容差
                    const padding = element.size / 2 + 3;
                    
                    return {
                        x: minX - padding,
                        y: minY - padding,
                        width: (maxX - minX) + 2 * padding,
                        height: (maxY - minY) + 2 * padding
                    };
                }
                return {x: 0, y: 0, width: 0, height: 0};
                
            default:
                return {x: 0, y: 0, width: 0, height: 0};
        }
    }

    /**
     * 绘制裁剪区域
     */
    drawCropArea() {
        if (this.cropArea) {
            var x = Math.min(this.cropArea.x, this.cropArea.x + this.cropArea.width);
            var y = Math.min(this.cropArea.y, this.cropArea.y + this.cropArea.height);
            var width = Math.abs(this.cropArea.width);
            var height = Math.abs(this.cropArea.height);
            
            this.ctx.save();
            
            // 绘制遮罩
            this.ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.globalCompositeOperation = "destination-out";
            this.ctx.fillRect(x, y, width, height);
            
            this.ctx.restore();
            
            // 绘制边框
            this.ctx.strokeStyle = "#007bff";
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([5, 5]);
            this.ctx.strokeRect(x, y, width, height);
            this.ctx.setLineDash([]);
        }
    }

    /**
     * 绘制形状预览
     * @param {number} startX - 起始X坐标
     * @param {number} startY - 起始Y坐标
     * @param {number} endX - 结束X坐标
     * @param {number} endY - 结束Y坐标
     */
    drawShapePreview(startX, startY, endX, endY) {
        this.ctx.save();
        
        var settings = this.currentTool === "ellipse" ? this.settings.ellipse : this.settings.rectangle;
        var shapeType = this.currentTool === "ellipse" ? "ellipse" : "rect";
        
        this.ctx.strokeStyle = settings.color;
        this.ctx.lineWidth = settings.stroke;
        this.ctx.setLineDash([5, 5]);
        
        this.ctx.beginPath();
        
        if (shapeType === "ellipse") {
            var centerX = startX + (endX - startX) / 2;
            var centerY = startY + (endY - startY) / 2;
            var radiusX = Math.abs(endX - startX) / 2;
            var radiusY = Math.abs(endY - startY) / 2;
            this.ctx.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, 2 * Math.PI);
        } else {
            var x = Math.min(startX, endX);
            var y = Math.min(startY, endY);
            var width = Math.abs(endX - startX);
            var height = Math.abs(endY - startY);
            this.ctx.roundRect(x, y, width, height, 10);
        }
        
        this.ctx.stroke();
        this.ctx.restore();
    }

    /**
     * 绘制箭头预览
     * @param {number} startX - 起始X坐标
     * @param {number} startY - 起始Y坐标
     * @param {number} endX - 结束X坐标
     * @param {number} endY - 结束Y坐标
     */
    drawArrowPreview(startX, startY, endX, endY) {
        this.ctx.save();
        
        var settings = this.settings.arrow || { color: "#ff0000", stroke: 3 };
        
        // 确保坐标是有限数值
        const validStartX = this.ensureFiniteValue(startX);
        const validStartY = this.ensureFiniteValue(startY);
        const validEndX = this.ensureFiniteValue(endX);
        const validEndY = this.ensureFiniteValue(endY);
        const validStroke = this.ensureFiniteValue(settings.stroke, 3);
        const validColor = settings.color || "#ff0000";
        
        // 如果坐标无效，则返回
        if (!this.areFiniteValues([validStartX, validStartY, validEndX, validEndY])) {
            console.warn("Invalid arrow preview coordinates:", {startX, startY, endX, endY});
            this.ctx.restore();
            return;
        }
        
        // 创建从箭尾到箭头的渐变线条（从细到粗）
        const gradient = this.ctx.createLinearGradient(validStartX, validStartY, validEndX, validEndY);
        gradient.addColorStop(0, validColor);
        gradient.addColorStop(0.3, validColor);
        gradient.addColorStop(1, validColor);
        
        this.ctx.strokeStyle = gradient;
        this.ctx.lineCap = "round";
        this.ctx.lineJoin = "round";
        
        // 绘制主线条的渐变效果（从细到粗）- 不使用虚线
        const steps = 20; // 分段数量，数值越大越平滑
        for (let i = 0; i < steps; i++) {
            const t1 = i / steps;
            const t2 = (i + 1) / steps;
            
            const startProgress = t1;
            const endProgress = t2;
            
            // 计算当前段的起点和终点
            const segmentStartX = validStartX + (validEndX - validStartX) * startProgress;
            const segmentStartY = validStartY + (validEndY - validStartY) * startProgress;
            const segmentEndX = validStartX + (validEndX - validStartX) * endProgress;
            const segmentEndY = validStartY + (validEndY - validStartY) * endProgress;
            
            // 线条宽度从细到粗
            const segmentWidth = validStroke * (0.3 + 0.7 * endProgress);
            this.ctx.lineWidth = segmentWidth;
            
            this.ctx.beginPath();
            this.ctx.moveTo(segmentStartX, segmentStartY);
            this.ctx.lineTo(segmentEndX, segmentEndY);
            this.ctx.stroke();
        }
        
        // 绘制箭头头部
        const angle = Math.atan2(validEndY - validStartY, validEndX - validStartX);
        const arrowLength = 15 + validStroke * 2; // 根据线宽调整箭头长度
        const arrowAngle = Math.PI / 6; // 箭头角度 (30度)
        
        // 箭头的两个点
        const arrowPoint1X = validEndX - arrowLength * Math.cos(angle - arrowAngle);
        const arrowPoint1Y = validEndY - arrowLength * Math.sin(angle - arrowAngle);
        const arrowPoint2X = validEndX - arrowLength * Math.cos(angle + arrowAngle);
        const arrowPoint2Y = validEndY - arrowLength * Math.sin(angle + arrowAngle);
        
        // 绘制箭头头部（更粗一些）
        this.ctx.lineWidth = settings.stroke * 1.5;
        this.ctx.beginPath();
        this.ctx.moveTo(endX, endY);
        this.ctx.lineTo(arrowPoint1X, arrowPoint1Y);
        this.ctx.moveTo(endX, endY);
        this.ctx.lineTo(arrowPoint2X, arrowPoint2Y);
        this.ctx.stroke();
        
        this.ctx.restore();
    }

    /**
     * 绘制高亮预览
     * @param {number} startX - 起始X坐标
     * @param {number} startY - 起始Y坐标
     * @param {number} endX - 结束X坐标
     * @param {number} endY - 结束Y坐标
     */
    drawHighlightPreview(startX, startY, endX, endY) {
        this.ctx.save();
        
        var x = Math.min(startX, endX);
        var y = Math.min(startY, endY);
        var width = Math.abs(endX - startX);
        var height = Math.abs(endY - startY);
        
        this.ctx.strokeStyle = "#ff0000";
        this.ctx.lineWidth = 4;
        this.ctx.setLineDash([5, 5]);
        
        this.drawRoundedRect(this.ctx, x, y, width, height, 8);
        this.ctx.stroke();
        
        this.ctx.restore();
    }

    // ===================== 属性面板 =====================

    /**
     * 显示属性面板
     * @param {Object} element - 元素对象
     */
    showPropertyPanel(element) {
        var panel = document.getElementById("propertyPanel");
        var content = document.getElementById("propertyContent");
        
        // 首先清除可能存在的多选状态提示，确保显示单选内容
        this.clearMultiSelectionStatus();
        
        this.setupPanelDrag(panel);
        
        // 获取元素边界信息
        var bounds = this.getElementBounds(element);
        // 确保边界值都是有效数字
        const safeX = this.ensureFiniteValue(bounds.x, 0);
        const safeY = this.ensureFiniteValue(bounds.y, 0);
        const safeWidth = this.ensureFiniteValue(bounds.width, 0);
        const safeHeight = this.ensureFiniteValue(bounds.height, 0);
        
        var coordsHtml = `
            <div class="property-item">
                <label>坐标</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 5px;">
                    <div>
                        <label style="font-size: 11px; color: #6c757d;">X坐标</label>
                        <input type="number" class="property-input" id="propX" value="${Math.round(safeX)}" style="width: 100%;" title="X坐标">
                    </div>
                    <div>
                        <label style="font-size: 11px; color: #6c757d;">Y坐标</label>
                        <input type="number" class="property-input" id="propY" value="${Math.round(safeY)}" style="width: 100%;" title="Y坐标">
                    </div>
                </div>
            </div>
            <div class="property-item">
                <label>尺寸</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 5px;">
                    <div>
                        <label style="font-size: 11px; color: #6c757d;">宽度</label>
                        <input type="number" class="property-input" id="propWidth" value="${Math.round(safeWidth)}" style="width: 100%;" title="宽度">
                    </div>
                    <div>
                        <label style="font-size: 11px; color: #6c757d;">高度</label>
                        <input type="number" class="property-input" id="propHeight" value="${Math.round(safeHeight)}" style="width: 100%;" title="高度">
                    </div>
                </div>
            </div>
        `;
        
        let specificHtml = '';
        
        switch(element.type) {
            case "text":
                specificHtml = `
                    <div class="property-item">
                        <label>文字内容</label>
                        <textarea class="property-input" id="propTextContent" rows="4" style="resize: vertical;">${element.content}</textarea>
                    </div>
                    <div class="property-item">
                        <label>颜色</label>
                        <input type="color" class="property-input" id="propTextColor" value="${element.color}">
                    </div>
                    <div class="property-item">
                        <label>大小</label>
                        <input type="range" class="property-input" id="propTextSize" min="12" max="72" value="${element.size}">
                    </div>
                    <div class="property-item">
                        <label>样式</label>
                        <div class="property-style-buttons">
                            <button class="property-style-button ${element.bold ? "active" : ""}" id="propTextBold" style="font-weight: bold;">B</button>
                            <button class="property-style-button ${element.italic ? "active" : ""}" id="propTextItalic" style="font-style: italic;">I</button>
                            <button class="property-style-button ${element.underline ? "active" : ""}" id="propTextUnderline" style="text-decoration: underline;">U</button>
                        </div>
                    </div>
                `;
                break;
                
            case "number":
                specificHtml = `
                    <div class="property-item">
                        <label>数字</label>
                        <input type="number" class="property-input" id="propNumber" min="1" max="99" value="${element.number}">
                    </div>
                    <div class="property-item">
                        <label>颜色</label>
                        <input type="color" class="property-input" id="propNumberColor" value="${element.color}">
                    </div>
                `;
                break;
                
            case "shape":
                specificHtml = `
                    <div class="property-item">
                        <label>颜色</label>
                        <input type="color" class="property-input" id="propShapeColor" value="${element.color}">
                    </div>
                    <div class="property-item">
                        <label>线宽</label>
                        <input type="range" class="property-input" id="propShapeStroke" min="1" max="10" value="${element.stroke}">
                    </div>
                `;
                break;
                
            case "arrow":
                specificHtml = `
                    <div class="property-item">
                        <label>颜色</label>
                        <input type="color" class="property-input" id="propArrowColor" value="${element.color}">
                    </div>
                    <div class="property-item">
                        <label>线宽</label>
                        <input type="range" class="property-input" id="propArrowStroke" min="1" max="10" value="${element.stroke}">
                    </div>
                `;
                break;
        }
        
        // 确保坐标信息始终显示在最前面
        let html = coordsHtml + specificHtml;
        content.innerHTML = html;
        panel.classList.add("active");
        
        // 更新工具选项区域，隐藏默认提示
        const selectOptions = document.getElementById("selectOptions");
        if (selectOptions) {
            const hintElement = selectOptions.querySelector('span:last-child');
            if (hintElement && hintElement.textContent === "点击选择已添加的元素进行编辑") {
                hintElement.textContent = "已选择元素，可以编辑属性";
                hintElement.style.color = "#28a745";
            }
        }
        
        // 更新工具选项显示（显示选中元素的对应选项）
        this.updateToolOptionsForSelection();
        
        this.bindPropertyEvents(element);
        this.bindPropertyPanelActions(element);
    }

    /**
     * 绑定属性事件
     * @param {Object} element - 元素对象
     */
    bindPropertyEvents(element) {
        let updateProperty = (property, value) => {
            // 确保值是有效数字（除了颜色、字体等属性）
            if (typeof value === 'number' && !isFinite(value)) {
                console.warn(`Invalid value for property ${property}:`, value);
                return;
            }
            element[property] = value;
            // 保持元素选择状态并自动保存
            this.saveState();  // 保存到历史记录
            this.render();
            // 重新刷新属性面板显示最新状态
            this.showPropertyPanel(element);
            this.showNotification(`属性已更新：${property}`, 'success');
        };
        
        // 坐标和尺寸事件绑定
        var bindCoordinateEvents = () => {
            var propX = document.getElementById("propX");
            var propY = document.getElementById("propY");
            var propWidth = document.getElementById("propWidth");
            var propHeight = document.getElementById("propHeight");
            
            if (propX) {
                propX.addEventListener("input", event => {
                    var newX = parseInt(event.target.value);
                    var deltaX = newX - element.x;
                    element.x = newX;
                    if (element.contentX !== undefined) element.contentX += deltaX;
                    // 保持选择状态并自动保存
                    this.saveState();
                    this.render();
                    this.showPropertyPanel(element);
                    this.showNotification(`X坐标已更新：${newX}px`, 'success');
                });
            }
            
            if (propY) {
                propY.addEventListener("input", event => {
                    var newY = parseInt(event.target.value);
                    var deltaY = newY - element.y;
                    element.y = newY;
                    if (element.contentY !== undefined) element.contentY += deltaY;
                    // 保持选择状态并自动保存
                    this.saveState();
                    this.render();
                    this.showPropertyPanel(element);
                    this.showNotification(`Y坐标已更新：${newY}px`, 'success');
                });
            }
            
            if (propWidth) {
                propWidth.addEventListener("input", event => {
                    var newWidth = parseInt(event.target.value);
                    if (element.type === "number") {
                        element.width = newWidth;
                    } else {
                        element.x2 = element.x + newWidth;
                    }
                    // 保持选择状态并自动保存
                    this.saveState();
                    this.render();
                    this.showPropertyPanel(element);
                    this.showNotification(`宽度已更新：${newWidth}px`, 'success');
                });
            }
            
            if (propHeight) {
                propHeight.addEventListener("input", event => {
                    var newHeight = parseInt(event.target.value);
                    if (element.type === "number") {
                        element.height = newHeight;
                    } else {
                        element.y2 = element.y + newHeight;
                    }
                    // 保持选择状态并自动保存
                    this.saveState();
                    this.render();
                    this.showPropertyPanel(element);
                    this.showNotification(`高度已更新：${newHeight}px`, 'success');
                });
            }
        };
        
        bindCoordinateEvents();
        
        var textContent = document.getElementById("propTextContent");
        if (textContent) {
            textContent.addEventListener("input", event => {
                updateProperty("content", event.target.value);
            });
        }
        
        var textColor = document.getElementById("propTextColor");
        if (textColor) {
            textColor.addEventListener("change", event => {
                updateProperty("color", event.target.value);
            });
        }
        
        var textSize = document.getElementById("propTextSize");
        if (textSize) {
            textSize.addEventListener("input", event => {
                updateProperty("size", parseInt(event.target.value));
            });
        }
        
        var textBold = document.getElementById("propTextBold");
        if (textBold) {
            textBold.addEventListener("click", () => {
                element.bold = !element.bold;
                textBold.classList.toggle("active", element.bold);
                // 保持选择状态并自动保存
                this.saveState();
                this.render();
                this.showPropertyPanel(element);
                this.showNotification(`粗体已${element.bold ? '开启' : '关闭'}`, 'success');
            });
        }
        
        var textItalic = document.getElementById("propTextItalic");
        if (textItalic) {
            textItalic.addEventListener("click", () => {
                element.italic = !element.italic;
                textItalic.classList.toggle("active", element.italic);
                // 保持选择状态并自动保存
                this.saveState();
                this.render();
                this.showPropertyPanel(element);
                this.showNotification(`斜体已${element.italic ? '开启' : '关闭'}`, 'success');
            });
        }
        
        var textUnderline = document.getElementById("propTextUnderline");
        if (textUnderline) {
            textUnderline.addEventListener("click", () => {
                element.underline = !element.underline;
                textUnderline.classList.toggle("active", element.underline);
                // 保持选择状态并自动保存
                this.saveState();
                this.render();
                this.showPropertyPanel(element);
                this.showNotification(`下划线已${element.underline ? '开启' : '关闭'}`, 'success');
            });
        }
        
        var propNumber = document.getElementById("propNumber");
        if (propNumber) {
            propNumber.addEventListener("input", event => {
                updateProperty("number", parseInt(event.target.value));
            });
        }
        
        var propNumberColor = document.getElementById("propNumberColor");
        if (propNumberColor) {
            propNumberColor.addEventListener("change", event => {
                updateProperty("color", event.target.value);
            });
        }
        
        var propShapeColor = document.getElementById("propShapeColor");
        if (propShapeColor) {
            propShapeColor.addEventListener("change", event => {
                updateProperty("color", event.target.value);
            });
        }
        
        var propShapeStroke = document.getElementById("propShapeStroke");
        if (propShapeStroke) {
            propShapeStroke.addEventListener("input", event => {
                updateProperty("stroke", parseInt(event.target.value));
            });
        }
        
        // 箭头属性绑定
        var propArrowColor = document.getElementById("propArrowColor");
        if (propArrowColor) {
            propArrowColor.addEventListener("change", event => {
                updateProperty("color", event.target.value);
            });
        }
        
        var propArrowStroke = document.getElementById("propArrowStroke");
        if (propArrowStroke) {
            propArrowStroke.addEventListener("input", event => {
                updateProperty("stroke", parseInt(event.target.value));
            });
        }
    }

    /**
     * 绑定属性面板操作按钮事件
     * @param {Object} element - 元素对象
     */
    bindPropertyPanelActions(element) {
        // 保存并继续编辑按钮
        var saveBtn = document.getElementById("savePropertyChanges");
        if (saveBtn) {
            saveBtn.addEventListener("click", () => {
                this.savePropertyChanges(element);
            });
        }

        // 关闭按钮 - 关闭面板但保持元素选中状态
        var closeBtn = document.getElementById("closePropertyPanel");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                this.closePropertyPanel();
            });
        }

        // 删除按钮保持原有的事件绑定
        var deleteBtn = document.getElementById("deleteElement");
        if (deleteBtn) {
            deleteBtn.addEventListener("click", this.deleteSelectedElement.bind(this));
        }
    }

    /**
     * 保存属性更改并继续编辑
     * @param {Object} element - 元素对象
     */
    savePropertyChanges(element) {
        // 现在属性修改已经是自动保存的了
        // 这个函数主要用于提示用户当前可以继续编辑
        this.showNotification('属性已自动保存，可以继续编辑', 'success');
        
        // 重新刷新属性面板显示最新状态
        this.showPropertyPanel(element);
    }

    /**
     * 关闭属性面板但保持元素选中状态（连续编辑）
     */
    closePropertyPanel() {
        const panel = document.getElementById("propertyPanel");
        panel.classList.remove("active");
        
        // 保持元素选中状态，允许连续编辑
        if (this.selectedElement) {
            this.render();
            this.showNotification('可以继续点击元素进行编辑', 'info');
        }
    }

    /**
     * 实时更新属性面板的值
     */
    updatePropertyPanelValues() {
        // 如果有多选元素，优先显示多选信息
        if (this.selectedElements.length > 0) {
            if (!document.getElementById("propertyPanel").classList.contains("active")) {
                return;
            }
            
            // 显示多选信息
            var count = this.selectedElements.length;
            var firstElement = this.selectedElements[0];
            var bounds = this.getElementBounds(firstElement);
            var propX = document.getElementById("propX");
            var propY = document.getElementById("propY");
            var propWidth = document.getElementById("propWidth");
            var propHeight = document.getElementById("propHeight");

            // 避免在输入框获得焦点时更新值（防止冲突）
            var activeElement = document.activeElement;
            if (activeElement && (activeElement.id === "propX" || activeElement.id === "propY" || 
                                  activeElement.id === "propWidth" || activeElement.id === "propHeight")) {
                return;
            }

            // 显示多选状态下的基本信息
            // 对于X坐标，显示选中元素数量
            if (propX) propX.value = count;  // 显示选中数量而非中文字符
            if (propY) propY.value = Math.round(bounds.y);
            if (propWidth) propWidth.value = Math.round(bounds.width);
            if (propHeight) propHeight.value = Math.round(bounds.height);
            
            // 创建一个提示来显示多选状态
            this.showMultiSelectionStatus(count);
            return;
        }
        
        // 单选元素处理
        if (!this.selectedElement || !document.getElementById("propertyPanel").classList.contains("active")) {
            return;
        }
        
        // 确保清除多选状态
        this.clearMultiSelectionStatus();

        var bounds = this.getElementBounds(this.selectedElement);
        var propX = document.getElementById("propX");
        var propY = document.getElementById("propY");
        var propWidth = document.getElementById("propWidth");
        var propHeight = document.getElementById("propHeight");

        // 避免在输入框获得焦点时更新值（防止冲突）
        var activeElement = document.activeElement;
        if (activeElement && (activeElement.id === "propX" || activeElement.id === "propY" || 
                              activeElement.id === "propWidth" || activeElement.id === "propHeight")) {
            return;
        }

        // 移除多选状态提示（切换到单选模式）
        this.clearMultiSelectionStatus();
        
        if (propX) propX.value = Math.round(bounds.x);
        if (propY) propY.value = Math.round(bounds.y);
        if (propWidth) propWidth.value = Math.round(bounds.width);
        if (propHeight) propHeight.value = Math.round(bounds.height);
    }

    /**
     * 清理多选状态提示
     */
    clearMultiSelectionStatus() {
        var panel = document.getElementById("propertyPanel");
        if (panel) {
            var existingStatus = panel.querySelector('.multi-selection-status');
            if (existingStatus) {
                existingStatus.remove();
            }
        }
        
        // 确保在切换到单选模式时更新工具选项显示
        this.updateToolOptionsForSelection();
    }

    /**
     * 显示多选状态提示
     * @param {number} count - 选中元素数量
     */
    showMultiSelectionStatus(count) {
        var panel = document.getElementById("propertyPanel");
        var content = document.getElementById("propertyContent");
        
        if (panel && content) {
            // 移除之前的提示
            var existingStatus = panel.querySelector('.multi-selection-status');
            if (existingStatus) {
                existingStatus.remove();
            }
            
            // 添加新的多选状态提示
            var statusDiv = document.createElement('div');
            statusDiv.className = 'multi-selection-status';
            statusDiv.style.cssText = `
                background: #e3f2fd;
                border: 1px solid #2196f3;
                border-radius: 4px;
                padding: 8px;
                margin: 10px 0;
                text-align: center;
                color: #1976d2;
                font-weight: bold;
                font-size: 12px;
            `;
            statusDiv.textContent = `已选中 ${count} 个元素`;
            
            // 在第一个属性项之前插入
            var firstProperty = content.querySelector('.property-item');
            if (firstProperty) {
                content.insertBefore(statusDiv, firstProperty);
            } else {
                content.appendChild(statusDiv);
            }
        }
    }

    /**
     * 设置面板拖拽功能
     * @param {HTMLElement} panel - 面板元素
     */
    setupPanelDrag(panel) {
        if (panel.dataset.dragSetup) {
            return;
        }
        
        panel.dataset.dragSetup = "true";
        
        var title = panel.querySelector(".property-title");
        let isDragging = false;
        let startX, startY;
        let originalLeft, originalTop;
        
        let onMouseMove = (event) => {
            var deltaX = event.clientX - startX;
            var deltaY = event.clientY - startY;
            
            let newLeft = originalLeft + deltaX;
            let newTop = originalTop + deltaY;
            
            let panelRect = panel.getBoundingClientRect();
            let maxX = window.innerWidth - panelRect.width;
            let maxY = window.innerHeight - panelRect.height;
            
            newLeft = Math.max(0, Math.min(newLeft, maxX));
            newTop = Math.max(0, Math.min(newTop, maxY));
            
            panel.style.left = newLeft + "px";
            panel.style.top = newTop + "px";
        };
        
        let onMouseUp = () => {
            isDragging = false;
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
        };
        
        title.addEventListener("mousedown", (event) => {
            isDragging = true;
            startX = event.clientX;
            startY = event.clientY;
            
            let panelRect = panel.getBoundingClientRect();
            originalLeft = panelRect.left;
            originalTop = panelRect.top;
            
            panel.style.position = "fixed";
            panel.style.left = originalLeft + "px";
            panel.style.top = originalTop + "px";
            panel.style.right = "auto";
            panel.style.transform = "none";
            
            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
            
            event.preventDefault();
        });
    }

    /**
     * 隐藏属性面板
     */
    hidePropertyPanel() {
        document.getElementById("propertyPanel").classList.remove("active");
        
        // 恢复工具选项区域的默认提示
        const selectOptions = document.getElementById("selectOptions");
        if (selectOptions) {
            const hintElement = selectOptions.querySelector('span:last-child');
            if (hintElement) {
                hintElement.textContent = "点击选择已添加的元素进行编辑";
                hintElement.style.color = "#6c757d";
            }
        }
        
        // 恢复选择工具选项的显示（当没有元素选中时）
        this.updateToolOptionsForSelection();
    }

    /**
     * 删除选中元素
     */
    deleteSelectedElement() {
        let deletedCount = 0;
        
        // 删除单选元素
        if (this.selectedElement) {
            let index = this.elements.indexOf(this.selectedElement);
            if (index > -1) {
                this.elements.splice(index, 1);
                deletedCount++;
            }
            this.selectedElement = null;
        }
        
        // 删除多选元素
        if (this.selectedElements.length > 0) {
            for (let element of this.selectedElements) {
                let index = this.elements.indexOf(element);
                if (index > -1) {
                    this.elements.splice(index, 1);
                    deletedCount++;
                }
            }
            this.selectedElements = [];
        }
        
        if (deletedCount > 0) {
            this.hidePropertyPanel();
            this.saveState();
            this.render();
            this.showNotification(`✅ 成功删除 ${deletedCount} 个元素`, 'success');
        }
    }

    // ===================== 历史记录和撤销 =====================

    /**
     * 保存状态到历史记录
     */
    saveState() {
        var state = {
            elements: JSON.parse(JSON.stringify(this.elements)),
            imageData: this.canvas.toDataURL()
        };
        
        this.history = this.history.slice(0, this.historyIndex + 1);
        this.history.push(state);
        this.historyIndex++;
        
        // 限制历史记录数量
        if (this.history.length > 20) {
            this.history.shift();
            this.historyIndex--;
        }
    }

    /**
     * 撤销操作
     */
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            var previousState = this.history[this.historyIndex];
            this.elements = JSON.parse(JSON.stringify(previousState.elements));
            
            let image = new Image;
            image.onload = () => {
                this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                this.ctx.drawImage(image, 0, 0);
                this.render();
            };
            image.src = previousState.imageData;
            
            image.src = previousState.imageData;
            this.selectedElement = null;
            this.hidePropertyPanel();
        }
    }

    /**
     * 保存图片
     */
    saveImage() {
        var canvas = document.createElement("canvas");
        let ctx = canvas.getContext("2d");
        canvas.width = this.canvas.width;
        canvas.height = this.canvas.height;
        
        if (this.backgroundImage) {
            ctx.drawImage(this.backgroundImage, 0, 0, canvas.width, canvas.height);
        }
        
        // 处理高亮遮罩
        var highlightElements = this.elements.filter(element => element.type === "highlight");
        
        if (highlightElements.length > 0) {
            var maskCanvas = document.createElement("canvas");
            maskCanvas.width = canvas.width;
            maskCanvas.height = canvas.height;
            
            let maskCtx = maskCanvas.getContext("2d");
            maskCtx.fillStyle = "rgba(0, 0, 0, 0.5)";
            maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
            maskCtx.globalCompositeOperation = "destination-out";
            
            highlightElements.forEach(element => {
                var x = Math.min(element.x, element.x + element.width);
                var y = Math.min(element.y, element.y + element.height);
                var width = Math.abs(element.width);
                var height = Math.abs(element.height);
                
                maskCtx.fillStyle = "rgba(255, 255, 255, 1)";
                this.drawRoundedRect(maskCtx, x, y, width, height, 8);
                maskCtx.fill();
            });
            
            ctx.drawImage(maskCanvas, 0, 0);
        }
        
        // 绘制所有元素
        this.elements.forEach(element => {
            if (element.type !== "highlight") {
                this.drawElementOnContext(ctx, element);
            }
        });
        
        var imageData = canvas.toDataURL();
        
        // 通知父窗口
        if (this.editorData && this.editorData.stepIndex !== undefined) {
            if (window.opener) {
                window.opener.postMessage({
                    action: "updateStepImage",
                    stepIndex: this.editorData.stepIndex,
                    imageData: imageData
                }, "*");
            } else {
                var updateData = {
                    action: "updateStepImage",
                    stepIndex: this.editorData.stepIndex,
                    imageData: imageData,
                    timestamp: Date.now()
                };
                localStorage.setItem("editorUpdate", JSON.stringify(updateData));
                window.dispatchEvent(new StorageEvent("storage", {
                    key: "editorUpdate",
                    newValue: JSON.stringify(updateData)
                }));
            }
            
            window.close();
        }
    }

    /**
     * 处理上传按钮点击
     */
    handleUpload() {
        this.fileInput.click();
    }

    /**
     * 从文件加载图片
     */
    loadImageFromFile(file) {
        if (!file.type.match("image.*")) {
            alert("请选择图片文件！");
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                // 设置画布大小为图片大小
                this.canvas.width = img.width;
                this.canvas.height = img.height;
                
                // 存储背景图片
                this.backgroundImage = img;
                
                // 存储原始图片的base64数据
                this.imageSrc = e.target.result;
                
                // 清空之前的所有元素
                this.elements = [];
                this.selectedElement = null;
                
                // 重新绘制画布
                this.render();
                
                // 隐藏拖拽上传区域
                this.hideDragDropArea();
                
                // 保存状态
                this.saveState();
                
                // 切换到选择工具
                this.setTool("select");
                this.updateToolbar("select");
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }

    /**
     * 下载图片
     */
    downloadImage() {
        var canvas = document.createElement("canvas");
        let ctx = canvas.getContext("2d");
        canvas.width = this.canvas.width;
        canvas.height = this.canvas.height;
        
        if (this.backgroundImage) {
            ctx.drawImage(this.backgroundImage, 0, 0, canvas.width, canvas.height);
        }
        
        // 处理高亮遮罩
        var highlightElements = this.elements.filter(element => element.type === "highlight");
        
        if (highlightElements.length > 0) {
            var maskCanvas = document.createElement("canvas");
            maskCanvas.width = canvas.width;
            maskCanvas.height = canvas.height;
            
            let maskCtx = maskCanvas.getContext("2d");
            maskCtx.fillStyle = "rgba(0, 0, 0, 0.5)";
            maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
            maskCtx.globalCompositeOperation = "destination-out";
            
            highlightElements.forEach(element => {
                var x = Math.min(element.x, element.x + element.width);
                var y = Math.min(element.y, element.y + element.height);
                var width = Math.abs(element.width);
                var height = Math.abs(element.height);
                
                maskCtx.fillStyle = "rgba(255, 255, 255, 1)";
                this.drawRoundedRect(maskCtx, x, y, width, height, 8);
                maskCtx.fill();
            });
            
            ctx.drawImage(maskCanvas, 0, 0);
        }
        
        // 绘制所有元素
        this.elements.forEach(element => {
            if (element.type !== "highlight") {
                this.drawElementOnContext(ctx, element);
            }
        });
        
        var link = document.createElement("a");
        link.download = "edited-image.png";
        link.href = canvas.toDataURL();
        link.click();
    }

    /**
     * 在指定上下文中绘制元素
     * @param {CanvasRenderingContext2D} ctx - 画布上下文
     * @param {Object} element - 元素对象
     */
    drawElementOnContext(ctx, element) {
        ctx.save();
        
        switch(element.type) {
            case "text":
                ctx.fillStyle = element.color;
                
                let fontWeight = "";
                if (element.bold) {
                    fontWeight += "bold ";
                }
                if (element.italic) {
                    fontWeight += "italic ";
                }
                
                let font = fontWeight + element.size + "px Arial";
                ctx.font = font;
                
                let lineHeight = 1.2 * element.size;
                let lines = element.content.split("\n");
                
                lines.forEach((line, index) => {
                    let y = element.y + index * lineHeight;
                    ctx.fillText(line, element.x, y);
                    
                    if (element.underline && line !== "") {
                        let textWidth = ctx.measureText(line).width;
                        ctx.beginPath();
                        ctx.moveTo(element.x, y + 2);
                        ctx.lineTo(element.x + textWidth, y + 2);
                        ctx.strokeStyle = element.color;
                        ctx.lineWidth = 1;
                        ctx.stroke();
                    }
                });
                break;
                
            case "number":
                var radius = element.size;
                ctx.fillStyle = element.color;
                ctx.beginPath();
                ctx.arc(element.x, element.y, radius, 0, 2 * Math.PI);
                ctx.fill();
                
                ctx.fillStyle = "white";
                ctx.font = "bold " + (1.2 * radius) + "px Arial";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(element.number.toString(), element.x, element.y);
                ctx.textAlign = "start";
                ctx.textBaseline = "alphabetic";
                break;
                
            case "shape":
                ctx.strokeStyle = element.color;
                ctx.lineWidth = element.stroke;
                ctx.beginPath();
                
                if (element.shapeType === "ellipse") {
                    var centerX = element.x + element.width / 2;
                    var centerY = element.y + element.height / 2;
                    var radiusX = Math.abs(element.width) / 2;
                    var radiusY = Math.abs(element.height) / 2;
                    ctx.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, 2 * Math.PI);
                } else {
                    var x = Math.min(element.x, element.x + element.width);
                    var y = Math.min(element.y, element.y + element.height);
                    var width = Math.abs(element.width);
                    var height = Math.abs(element.height);
                    ctx.roundRect(x, y, width, height, 10);
                }
                
                ctx.stroke();
                break;
                
            case "brush":
                if (element.points && element.points.length >= 2) {
                    ctx.strokeStyle = element.color;
                    ctx.lineWidth = element.size;
                    ctx.lineCap = "round";
                    ctx.lineJoin = "round";
                    
                    ctx.beginPath();
                    ctx.moveTo(element.points[0].x, element.points[0].y);
                    
                    for (let i = 1; i < element.points.length; i++) {
                        ctx.lineTo(element.points[i].x, element.points[i].y);
                    }
                    
                    ctx.stroke();
                }
                break;
                
            case "mosaic":
                if (element.points && element.points.length > 0) {
                    let size = element.size;
                    let intensity = element.intensity;
                    
                    element.points.forEach(point => {
                        this.applyMosaicAtPointOnContext(ctx, point.x, point.y, size, intensity);
                    });
                }
                break;
        }
        
        ctx.restore();
    }

    /**
     * 在指定上下文中应用马赛克效果
     * @param {CanvasRenderingContext2D} ctx - 画布上下文
     * @param {number} x - X坐标
     * @param {number} y - Y坐标
     * @param {number} size - 马赛克大小
     * @param {number} intensity - 马赛克强度
     */
    applyMosaicAtPointOnContext(ctx, x, y, size, intensity) {
        var imageData = ctx.getImageData(x - size/2, y - size/2, size, size);
        var data = imageData.data;
        
        for (let i = 0; i < data.length; i += 4) {
            var pixelIndex = Math.floor(i / 4);
            var blockX = Math.floor(pixelIndex % size / intensity) * intensity;
            var blockIndex = 4 * (Math.floor(Math.floor(pixelIndex / size) / intensity) * intensity * size + blockX);
            
            if (blockIndex < data.length) {
                data[i] = data[blockIndex];
                data[i + 1] = data[blockIndex + 1];
                data[i + 2] = data[blockIndex + 2];
            }
        }
        
        ctx.putImageData(imageData, x - size/2, y - size/2);
    }

    /**
     * 绘制元素边界框（用于高亮显示）
     * @param {CanvasRenderingContext2D} ctx - 画布上下文
     * @param {Object} element - 元素对象
     */
    drawElementBounds(ctx, element) {
        const bounds = this.getElementBounds(element);
        ctx.strokeRect(bounds.x, bounds.y, bounds.width, bounds.height);
    }

    /**
     * 导出元素到JSON文件
     */
    async exportElementsToJson() {
        try {
            // 显示进度提示
            this.showNotification("🔄 正在生成元素截图...", "info");
            
            // 获取基本画布信息
            const canvasData = {
                canvasWidth: this.canvas.width,
                canvasHeight: this.canvas.height,
                imageSrc: this.imageSrc || null, // 包含原始图片的base64数据
                exportTime: new Date().toISOString(),
                version: "1.9" // 升级版本号以支持截图功能
            };

            // 获取所有元素并为每个元素生成截图
            const elementsWithScreenshots = [];
            
            for (let i = 0; i < this.elements.length; i++) {
                const element = this.elements[i];
                
                // 创建元素的深拷贝
                const elementCopy = JSON.parse(JSON.stringify(element));
                
                // 添加name字段，格式为 sc_1.png, sc_2.png, ...
                elementCopy.name = `sc_${i + 1}.png`;
                
                // 为每个元素生成截图
                const screenshot = await this.generateElementScreenshot(element, i);
                if (screenshot) {
                    elementCopy.screenshot = screenshot; // 添加截图到elements字段
                }
                
                elementsWithScreenshots.push(elementCopy);
                
                // 更新进度
                const progress = Math.round(((i + 1) / this.elements.length) * 100);
                this.showNotification(`🔄 正在生成元素截图... ${progress}%`, "info");
            }

            const elementsData = {
                elements: elementsWithScreenshots,
                totalCount: this.elements.length
            };

            // 合并数据
            const exportData = {
                ...canvasData,
                ...elementsData
            };

            // 创建JSON字符串
            const jsonString = JSON.stringify(exportData, null, 2);

            // 创建下载链接
            const blob = new Blob([jsonString], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            // 创建下载链接并触发下载
            const link = document.createElement('a');
            link.href = url;
            link.download = `snapscribe-elements-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // 清理URL对象
            URL.revokeObjectURL(url);
            
            // 显示成功消息
            const hasImage = exportData.imageSrc ? "(包含原始图片)" : "(无原始图片)";
            this.showNotification(`✅ 成功导出 ${this.elements.length} 个元素 ${hasImage}`, "success");
            
        } catch (error) {
            console.error('导出JSON时出错:', error);
            this.showNotification("❌ 导出失败: " + error.message, "error");
        }
    }

    /**
     * 为指定元素生成截图
     * @param {Object} element - 元素对象
     * @param {number} elementIndex - 元素索引
     * @returns {Promise<string>} 截图的base64字符串
     */
    async generateElementScreenshot(element, elementIndex) {
        return new Promise((resolve) => {
            try {
                // 创建临时画布
                const tempCanvas = document.createElement('canvas');
                const tempCtx = tempCanvas.getContext('2d');
                
                // 尝试使用元素尺寸，如果不存在则使用默认值
                const elementWidth = element.width || element.bounds?.width || 100;
                const elementHeight = element.height || element.bounds?.height || 100;
                
                // 设置画布大小为元素的边界框大小
                tempCanvas.width = Math.max(elementWidth, 1);
                tempCanvas.height = Math.max(elementHeight, 1);
                
                // 清除画布
                tempCtx.clearRect(0, 0, tempCanvas.width, tempCanvas.height);
                
                // 创建另一个临时画布用于渲染整个画布
                const renderCanvas = document.createElement('canvas');
                const renderCtx = renderCanvas.getContext('2d');
                
                renderCanvas.width = this.canvas.width;
                renderCanvas.height = this.canvas.height;
                
                // 清空渲染画布
                renderCtx.clearRect(0, 0, renderCanvas.width, renderCanvas.height);
                
                // 渲染背景图片（如果存在）
                if (this.backgroundImage) {
                    renderCtx.drawImage(this.backgroundImage, 0, 0);
                }
                
                // 渲染所有元素（用于参考背景）
                this.elements.forEach((el, idx) => {
                    if (idx === elementIndex) {
                        // 当前元素用红色边框高亮显示
                        this.drawElementOnContext(renderCtx, el);
                        // 添加红色边框高亮
                        renderCtx.strokeStyle = '#ff0000';
                        renderCtx.lineWidth = 3;
                        this.drawElementBounds(renderCtx, el);
                    } else {
                        // 其他元素正常渲染，但降低透明度
                        renderCtx.globalAlpha = 0.3;
                        this.drawElementOnContext(renderCtx, el);
                        renderCtx.globalAlpha = 1.0;
                    }
                });
                
                // 计算元素的实际绘制位置
                const bounds = element.bounds || {
                    x: element.x || 0,
                    y: element.y || 0,
                    width: elementWidth,
                    height: elementHeight
                };
                
                // 裁剪出元素区域
                tempCtx.drawImage(
                    renderCanvas,
                    Math.max(bounds.x, 0),  // 源x坐标
                    Math.max(bounds.y, 0),  // 源y坐标
                    Math.min(bounds.width, renderCanvas.width - Math.max(bounds.x, 0)),  // 源宽度
                    Math.min(bounds.height, renderCanvas.height - Math.max(bounds.y, 0)), // 源高度
                    0,  // 目标x坐标
                    0,  // 目标y坐标
                    Math.min(bounds.width, renderCanvas.width), // 目标宽度
                    Math.min(bounds.height, renderCanvas.height) // 目标高度
                );
                
                // 转换为base64字符串
                const screenshot = tempCanvas.toDataURL('image/png', 0.9);
                resolve(screenshot);
                
            } catch (error) {
                console.error('生成元素截图时出错:', error);
                resolve(null);
            }
        });
    }

    /**
     * 从JSON文件导入元素
     */
    importElementsFromJson(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        
        reader.onload = (e) => {
            try {
                const jsonData = JSON.parse(e.target.result);
                
                // 验证JSON格式
                if (!jsonData.elements || !Array.isArray(jsonData.elements)) {
                    throw new Error('无效的JSON格式：缺少elements数组');
                }

                // 确认导入
                const hasImage = jsonData.imageSrc ? " (包含原始图片)" : "";
                if (!confirm(`确定要导入 ${jsonData.elements.length} 个元素${hasImage}吗？这将清空当前画布。`)) {
                    return;
                }

                // 清空当前元素
                this.elements = [];
                this.selectedElement = null;
                this.hidePropertyPanel();

                // 导入新元素
                jsonData.elements.forEach(elementData => {
                    // 验证元素数据完整性
                    if (elementData.type) {
                        this.elements.push(elementData);
                    }
                });

                // 如果JSON包含原始图片数据，则恢复图片
                if (jsonData.imageSrc) {
                    this.imageSrc = jsonData.imageSrc;
                    const img = new Image();
                    img.onload = () => {
                        this.backgroundImage = img;
                        // 设置画布大小为图片大小
                        this.canvas.width = img.width;
                        this.canvas.height = img.height;
                        this.render();
                    };
                    img.src = jsonData.imageSrc;
                } else {
                    // 如果没有图片数据，清空背景
                    this.backgroundImage = null;
                    this.imageSrc = null;
                }

                // 重新渲染
                this.render();
                
                // 显示成功消息
                this.showNotification(`✅ 成功导入 ${this.elements.length} 个元素${hasImage}`, "success");
                
            } catch (error) {
                console.error('导入JSON时出错:', error);
                this.showNotification("❌ 导入失败: " + error.message, "error");
            }
        };
        
        reader.onerror = () => {
            this.showNotification("❌ 文件读取失败", "error");
        };
        
        reader.readAsText(file);
        
        // 清空input值，允许重复选择同一文件
        event.target.value = '';
    }

    /**
     * 显示通知消息
     */
    showNotification(message, type = "info") {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // 添加样式
        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '4px',
            color: 'white',
            fontSize: '14px',
            fontWeight: '500',
            zIndex: '9999',
            opacity: '0',
            transition: 'opacity 0.3s ease',
            maxWidth: '300px',
            wordWrap: 'break-word'
        });

        // 设置背景颜色
        switch(type) {
            case 'success':
                notification.style.backgroundColor = '#28a745';
                break;
            case 'error':
                notification.style.backgroundColor = '#dc3545';
                break;
            case 'warning':
                notification.style.backgroundColor = '#ffc107';
                notification.style.color = '#212529';
                break;
            default:
                notification.style.backgroundColor = '#17a2b8';
        }

        // 添加到页面
        document.body.appendChild(notification);
        
        // 显示动画
        setTimeout(() => {
            notification.style.opacity = '1';
        }, 10);
        
        // 自动隐藏
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    /**
     * 设置拖拽上传功能
     */
    setupDragAndDrop() {
        const dragDropArea = document.getElementById('dragDropArea');
        
        // 拖拽事件
        dragDropArea.addEventListener('dragenter', this.handleDragEnter.bind(this));
        dragDropArea.addEventListener('dragover', this.handleDragOver.bind(this));
        dragDropArea.addEventListener('dragleave', this.handleDragLeave.bind(this));
        dragDropArea.addEventListener('drop', this.handleDrop.bind(this));
        
        // 点击事件（作为文件选择的后备方式）
        dragDropArea.addEventListener('click', () => {
            this.fileInput.click();
        });
    }
    
    /**
     * 处理拖拽进入
     */
    handleDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        const dragDropArea = document.getElementById('dragDropArea');
        dragDropArea.classList.add('drag-over');
    }
    
    /**
     * 处理拖拽悬停
     */
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        const dragDropArea = document.getElementById('dragDropArea');
        dragDropArea.classList.add('drag-over');
    }
    
    /**
     * 处理拖拽离开
     */
    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // 只有当鼠标完全离开拖拽区域时才移除样式
        const rect = document.getElementById('dragDropArea').getBoundingClientRect();
        const x = e.clientX;
        const y = e.clientY;
        
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            const dragDropArea = document.getElementById('dragDropArea');
            dragDropArea.classList.remove('drag-over');
        }
    }
    
    /**
     * 处理拖拽放置
     */
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const dragDropArea = document.getElementById('dragDropArea');
        dragDropArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            const file = files[0];
            if (file.type.match('image.*')) {
                this.loadImageFromFile(file);
            } else {
                alert('请拖拽图片文件！');
            }
        }
    }
    
    /**
     * 显示拖拽上传区域
     */
    showDragDropArea() {
        const dragDropArea = document.getElementById('dragDropArea');
        const dragDropContainer = document.querySelector('.drag-drop-container');
        
        if (dragDropArea) {
            dragDropArea.classList.add('active');
        }
        
        if (dragDropContainer) {
            dragDropContainer.classList.add('active');
        }
    }
    
    /**
     * 隐藏拖拽上传区域
     */
    hideDragDropArea() {
        const dragDropArea = document.getElementById('dragDropArea');
        const dragDropContainer = document.querySelector('.drag-drop-container');
        
        if (dragDropArea) {
            dragDropArea.classList.remove('active');
        }
        
        if (dragDropContainer) {
            dragDropContainer.classList.remove('active');
        }
    }

    /**
     * 取消编辑
     */
    cancel() {
        if (confirm("确定要取消编辑吗？所有更改将丢失。")) {
            window.close();
        }
    }
    
    /**
     * 显示截图管理抽屉 - 与CSS动画保持一致
     */
    showScreenshotsDrawer() {
        const overlay = document.getElementById('screenshotsOverlay');
        const drawer = document.querySelector('.screenshots-drawer');
        
        if (overlay) {
            overlay.style.display = 'flex';
            // 使用requestAnimationFrame确保DOM更新后再添加show类
            setTimeout(() => {
                if (drawer) {
                    drawer.classList.add('show');
                }
            }, 10);
        }
        
        // 加载所有rect元素到列表
        this.loadScreenshotsList();
    }
    
    /**
     * 隐藏截图管理抽屉 - 与CSS动画保持一致
     */
    hideScreenshotsDrawer() {
        const overlay = document.getElementById('screenshotsOverlay');
        const drawer = document.querySelector('.screenshots-drawer');
        
        if (drawer) {
            drawer.classList.remove('show');
        }
        
        // 等待动画完成后隐藏遮罩层
        setTimeout(() => {
            if (overlay) {
                overlay.style.display = 'none';
            }
        }, 300);
    }
    
    /**
     * 加载截图列表
     */
    loadScreenshotsList() {
        const listContainer = document.getElementById('screenshotsList');
        if (!listContainer) return;
        
        // 清空现有内容
        listContainer.innerHTML = '';
        
        // 获取所有rect类型的元素及其在原始数组中的索引
        const rectElements = [];
        this.elements.forEach((element, originalIndex) => {
            if (element.type === 'shape' && element.shapeType === 'rect') {
                // 如果元素没有name，生成默认名称
                if (!element.name) {
                    const rectIndex = rectElements.length + 1;
                    element.name = `sc_${rectIndex}.png`;
                }
                rectElements.push({
                    element: element,
                    originalIndex: originalIndex,
                    rectIndex: rectElements.length
                });
            }
        });
        
        if (rectElements.length === 0) {
            listContainer.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 40px;">暂无矩形元素</p>';
            return;
        }
        
        // 为每个rect元素创建列表项
        rectElements.forEach((rectInfo) => {
            const item = this.createScreenshotListItem(rectInfo);
            listContainer.appendChild(item);
        });
    }
    
    /**
     * 创建截图列表项 - 每次都重新生成实时截图
     */
    createScreenshotListItem(rectInfo) {
        const item = document.createElement('div');
        item.className = 'screenshot-item';
        item.dataset.originalIndex = rectInfo.originalIndex;
        item.dataset.rectIndex = rectInfo.rectIndex;
        
        const element = rectInfo.element;
        
        // 生成或获取元素名称
        const elementName = element.name;
        
        // 创建标题行
        const header = document.createElement('div');
        header.className = 'screenshot-header';
        
        // 创建编号显示
        const numberBadge = document.createElement('div');
        numberBadge.className = 'screenshot-number';
        numberBadge.textContent = `${rectInfo.rectIndex + 1}`;
        numberBadge.style.cssText = `
            background: #007bff;
            color: white;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            margin-right: 8px;
            flex-shrink: 0;
        `;
        
        // 创建名称容器
        const nameContainer = document.createElement('div');
        nameContainer.style.flex = '1';
        nameContainer.style.display = 'flex';
        nameContainer.style.alignItems = 'center';
        
        // 创建可编辑的名称输入框
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'screenshot-name';
        nameInput.value = elementName;
        nameInput.dataset.originalName = elementName;
        nameInput.dataset.originalIndex = rectInfo.originalIndex;
        nameInput.style.flex = '1';
        nameInput.style.padding = '8px 12px';
        nameInput.style.height = '36px';
        nameInput.style.border = '1px solid #dee2e6';
        nameInput.style.borderRadius = '4px';
        nameInput.style.fontSize = '14px';
        
        // 添加双击编辑功能
        nameInput.addEventListener('dblclick', (e) => {
            e.target.focus();
            e.target.select();
        });
        
        // 添加回车键确认编辑
        nameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.target.blur();
            }
        });
        
        // 添加失焦事件保存更改
        nameInput.addEventListener('blur', (e) => {
            const newName = e.target.value.trim();
            const originalName = e.target.dataset.originalName;
            
            if (newName !== originalName && newName) {
                // 使用原始数组索引直接更新元素名称
                const originalIndex = parseInt(e.target.dataset.originalIndex);
                if (this.elements[originalIndex] && this.elements[originalIndex].type === 'shape' && this.elements[originalIndex].shapeType === 'rect') {
                    this.elements[originalIndex].name = newName;
                    e.target.dataset.originalName = newName;
                }
            }
        });
        
        // 创建操作按钮容器
        const actionButtons = document.createElement('div');
        actionButtons.style.display = 'flex';
        actionButtons.style.gap = '4px';
        actionButtons.style.marginLeft = '8px';
        
        // 创建下载按钮
        const downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'download-single-btn';
        downloadBtn.textContent = '下载';
        downloadBtn.title = '下载此截图';
        downloadBtn.style.cssText = `
            padding: 4px 8px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            flex-shrink: 0;
        `;
        downloadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.downloadSingleScreenshot(element, rectInfo.originalIndex);
        });
        
        // 创建删除按钮
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'delete-single-btn';
        deleteBtn.textContent = '删除';
        deleteBtn.title = '删除此截图元素';
        deleteBtn.style.cssText = `
            padding: 4px 8px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            flex-shrink: 0;
        `;
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.deleteSingleScreenshot(element, rectInfo.originalIndex);
        });
        
        // 组装操作按钮
        actionButtons.appendChild(downloadBtn);
        actionButtons.appendChild(deleteBtn);
        
        // 组装标题行
        nameContainer.appendChild(nameInput);
        nameContainer.appendChild(actionButtons);
        header.appendChild(numberBadge);
        header.appendChild(nameContainer);
        item.appendChild(header);
        
        // 创建预览区域
        const preview = document.createElement('div');
        preview.className = 'screenshot-preview';
        
        // 总是重新生成截图，确保显示最新状态
        if (this.backgroundImage) {
            // 显示"正在生成实时截图..."状态
            const statusText = document.createElement('div');
            statusText.style.cssText = 'color: #007bff; text-align: center; padding: 12px; font-size: 12px;';
            statusText.innerHTML = '<div style="margin-bottom: 6px;">🔄</div><div>正在生成实时截图...</div>';
            preview.appendChild(statusText);
            
            // 异步重新生成截图（基于当前rect大小）
            this.generateElementScreenshot(element, rectInfo.originalIndex).then(screenshot => {
                if (screenshot) {
                    // 更新元素数据
                    element.screenshot = screenshot;
                    
                    // 重新渲染预览
                    preview.innerHTML = '';
                    const img = document.createElement('img');
                    img.src = screenshot;
                    img.alt = elementName;
                    img.style.maxWidth = '100%';
                    img.style.maxHeight = '100%';
                    img.style.objectFit = 'contain';
                    preview.appendChild(img);
                } else {
                    // 生成失败，显示占位符
                    statusText.textContent = '实时截图生成失败';
                    statusText.style.color = '#dc3545';
                    statusText.innerHTML = '<div style="margin-bottom: 8px;">❌</div><div>实时截图生成失败</div>';
                }
            }).catch(error => {
                console.error('生成实时截图失败:', error);
                statusText.textContent = '实时截图生成失败';
                statusText.style.color = '#dc3545';
                statusText.innerHTML = '<div style="margin-bottom: 8px;">❌</div><div>实时截图生成失败</div>';
            });
        } else {
            // 如果没有背景图片，显示占位符
            const placeholder = document.createElement('div');
            placeholder.style.cssText = 'color: #6c757d; text-align: center; padding: 12px; font-size: 12px;';
            placeholder.innerHTML = '<div style="margin-bottom: 6px;">📷</div><div>请先上传图片</div>';
            preview.appendChild(placeholder);
        }
        
        item.appendChild(preview);
        
        return item;
    }
    
    /**
     * 一键导出所有截图
     */
    async exportAllScreenshots() {
        // 获取所有rect类型的元素
        const rectElements = [];
        this.elements.forEach((element, index) => {
            if (element.type === 'shape' && element.shapeType === 'rect') {
                // 确保元素有名称
                if (!element.name) {
                    const rectIndex = rectElements.length + 1;
                    element.name = `sc_${rectIndex}.png`;
                }
                rectElements.push({
                    element: element,
                    index: index
                });
            }
        });

        if (rectElements.length === 0) {
            this.showNotification('没有找到可导出的截图元素！', 'warning');
            this.hideScreenshotsDrawer();
            return;
        }

        // 显示开始导出的提示
        this.showNotification('正在生成截图...', 'info');

        try {
            // 为每个元素生成截图并下载
            for (let i = 0; i < rectElements.length; i++) {
                const { element, index } = rectElements[i];
                
                try {
                    // 生成截图
                    const screenshot = await this.generateElementScreenshot(element, index);
                    
                    if (screenshot) {
                        // 清理文件名：移除扩展名（如果存在），确保以.png结尾
                        let filename = element.name || `sc_${i + 1}.png`;
                        if (!filename.toLowerCase().endsWith('.png')) {
                            filename = filename.replace(/\.[^/.]+$/, '') + '.png';
                        }
                        
                        // 创建下载链接
                        const link = document.createElement('a');
                        link.href = screenshot;
                        link.download = filename;
                        link.style.display = 'none';
                        
                        // 添加到页面并点击
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        
                        // 短暂延迟，避免浏览器阻止多个下载
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }
                } catch (error) {
                    console.error(`生成第${i + 1}个截图失败:`, error);
                }
            }
            
            this.showNotification(`成功导出 ${rectElements.length} 个截图！`, 'success');
        } catch (error) {
            console.error('导出截图时发生错误:', error);
            this.showNotification('导出截图时发生错误，请重试', 'error');
        }
        
        // 关闭抽屉
        this.hideScreenshotsDrawer();
    }

    /**
     * 下载单个截图
     */
    async downloadSingleScreenshot(element, elementIndex) {
        try {
            // 生成截图
            const screenshot = await this.generateElementScreenshot(element, elementIndex);
            
            if (screenshot) {
                // 清理文件名：确保以.png结尾
                let filename = element.name || 'screenshot.png';
                if (!filename.toLowerCase().endsWith('.png')) {
                    filename = filename.replace(/\.[^/.]+$/, '') + '.png';
                }
                
                // 创建下载链接
                const link = document.createElement('a');
                link.href = screenshot;
                link.download = filename;
                link.style.display = 'none';
                
                // 添加到页面并点击
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                this.showNotification(`截图 "${filename}" 下载成功！`, 'success');
            } else {
                this.showNotification('截图生成失败！', 'error');
            }
        } catch (error) {
            console.error('下载截图时出错:', error);
            this.showNotification('下载截图时出错，请重试', 'error');
        }
    }

    /**
     * 删除单个截图元素
     */
    deleteSingleScreenshot(element, elementIndex) {
        const elementName = element.name || '未命名截图';
        
        // 使用自定义模态对话框
        this.showDeleteModal(elementName, (confirmed) => {
            if (!confirmed) {
                return; // 用户点击取消，不执行删除操作
            }
            
            try {
                // 从elements数组中删除元素
                if (this.elements[elementIndex] === element) {
                    this.elements.splice(elementIndex, 1);
                    
                    // 重新渲染画布
                    this.render();
                    
                    // 刷新截图列表
                    this.loadScreenshotsList();
                    
                    this.showNotification(`截图 "${elementName}" 已删除！`, 'success');
                } else {
                    // 如果直接匹配失败，尝试查找并删除
                    const foundIndex = this.elements.findIndex(el => el === element);
                    if (foundIndex !== -1) {
                        this.elements.splice(foundIndex, 1);
                        this.render();
                        this.loadScreenshotsList();
                        this.showNotification(`截图 "${elementName}" 已删除！`, 'success');
                    } else {
                        this.showNotification('找不到要删除的元素！', 'error');
                    }
                }
            } catch (error) {
                console.error('删除截图时出错:', error);
                this.showNotification('删除截图时出错，请重试', 'error');
            }
        });
    }
    
    /**
     * 显示自定义删除确认模态对话框
     */
    showDeleteModal(elementName, callback) {
        const modal = document.getElementById('deleteModal');
        const message = modal.querySelector('.delete-modal-message');
        const cancelBtn = document.getElementById('deleteCancelBtn');
        const confirmBtn = document.getElementById('deleteConfirmBtn');
        
        // 设置删除元素的名称
        message.textContent = `您确定要删除截图 "${elementName}" 吗？`;
        
        // 显示模态对话框
        modal.style.display = 'flex';
        
        // 绑定事件处理器
        const handleCancel = () => {
            this.hideDeleteModal();
            callback(false);
            cleanup();
        };
        
        const handleConfirm = () => {
            this.hideDeleteModal();
            callback(true);
            cleanup();
        };
        
        const handleOverlayClick = (e) => {
            if (e.target === modal) {
                handleCancel();
            }
        };
        
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                handleCancel();
            } else if (e.key === 'Enter') {
                handleConfirm();
            }
        };
        
        const cleanup = () => {
            cancelBtn.removeEventListener('click', handleCancel);
            confirmBtn.removeEventListener('click', handleConfirm);
            modal.removeEventListener('click', handleOverlayClick);
            document.removeEventListener('keydown', handleKeyDown);
        };
        
        // 添加事件监听器
        cancelBtn.addEventListener('click', handleCancel);
        confirmBtn.addEventListener('click', handleConfirm);
        modal.addEventListener('click', handleOverlayClick);
        document.addEventListener('keydown', handleKeyDown);
        
        // 聚焦确认按钮
        setTimeout(() => {
            confirmBtn.focus();
        }, 100);
    }
    
    /**
     * 隐藏删除确认模态对话框
     */
    hideDeleteModal() {
        const modal = document.getElementById('deleteModal');
        modal.style.display = 'none';
    }
    /**
     * 根据URL参数中的鼠标坐标自动生成矩形
     * @param {string} mouseParam - 鼠标坐标参数字符串，格式: "(x,y)"
     */
    generateRectFromMouseParam(mouseParam) {
        try {
            // 解析坐标参数: "(x,y)" -> {x, y}
            const coordMatch = mouseParam.match(/\((\d+),\s*(\d+)\)/);
            if (!coordMatch) {
                console.warn('鼠标坐标参数格式错误:', mouseParam);
                this.showNotification('鼠标坐标参数格式错误，应为: mouse=(x,y)', 'warning');
                return;
            }
            
            const centerX = parseInt(coordMatch[1]);
            const centerY = parseInt(coordMatch[2]);
            
            // 默认矩形尺寸
            const defaultWidth = 240;
            const defaultHeight = 60;
            
            // 计算矩形的左上角坐标
            const rectX = centerX - defaultWidth / 2;
            const rectY = centerY - defaultHeight / 2;
            
            // 检查矩形是否在画布范围内
            const canvasWidth = this.canvas.width;
            const canvasHeight = this.canvas.height;
            
            // 调整矩形位置，确保不会超出画布边界
            let finalX = Math.max(0, rectX);
            let finalY = Math.max(0, rectY);
            let finalWidth = defaultWidth;
            let finalHeight = defaultHeight;
            
            // 如果超出右边界，调整位置和宽度
            if (finalX + finalWidth > canvasWidth) {
                finalX = Math.max(0, canvasWidth - finalWidth);
            }
            
            // 如果超出下边界，调整位置和高度
            if (finalY + finalHeight > canvasHeight) {
                finalY = Math.max(0, canvasHeight - finalHeight);
            }
            
            // 创建矩形元素
            const rectElement = {
                type: "shape",
                shapeType: "rect",
                x: finalX,
                y: finalY,
                width: finalWidth,
                height: finalHeight,
                color: "#ff0000",
                stroke: 2,
                opacity: 1,
                fill: false,
                name: `auto_rect_${Date.now()}`,
                // 添加坐标信息到元素数据中，用于调试
                autoGenerated: true,
                centerX: centerX,
                centerY: centerY
            };
            
            // 添加到元素数组
            this.elements.push(rectElement);
            
            // 重新渲染画布
            this.render();
            
            // 显示成功提示
            this.showNotification(`自动生成矩形: 中心点(${centerX}, ${centerY}), 尺寸(${finalWidth}x${finalHeight})`, 'success');
            
            console.log('自动生成矩形:', rectElement);
            
        } catch (error) {
            console.error('解析鼠标坐标参数失败:', error);
            this.showNotification('解析鼠标坐标参数失败', 'error');
        }
    }

    /**
     * 全选所有元素 (Ctrl+A)
     */
    selectAllElements() {
        if (this.elements.length > 0) {
            this.selectedElement = null; // 清除单选
            this.selectedElements = [...this.elements]; // 复制所有元素到多选
            this.showPropertyPanel(this.elements[0]);
            this.render();
            this.showNotification(`✅ 已选中 ${this.elements.length} 个元素`, 'info');
        } else {
            this.showNotification('⚠️ 没有可选择的元素', 'warning');
        }
    }

    /**
     * 复制选中的元素 (Ctrl+C)
     */
    copySelectedElements() {
        this.clipboard = [];
        
        if (this.selectedElements.length > 0) {
            // 复制多选元素
            this.clipboard = this.selectedElements.map(element => {
                // 深度复制元素对象
                return JSON.parse(JSON.stringify(element));
            });
        } else if (this.selectedElement) {
            // 复制单选元素
            this.clipboard = [JSON.parse(JSON.stringify(this.selectedElement))];
        }
        
        if (this.clipboard.length > 0) {
            this.showNotification(`✅ 已复制 ${this.clipboard.length} 个元素`, 'info');
        } else {
            this.showNotification('⚠️ 没有选中的元素可复制', 'warning');
        }
    }

    /**
     * 粘贴复制的元素 (Ctrl+V)
     */
    pasteElements() {
        if (this.clipboard.length === 0) {
            this.showNotification('⚠️ 剪贴板中没有可粘贴的元素', 'warning');
            return;
        }
        
        let pastedCount = 0;
        let newElements = [];
        
        for (let copiedElement of this.clipboard) {
            // 创建新元素，添加偏移
            let newElement = JSON.parse(JSON.stringify(copiedElement));
            newElement.x += this.clipboardOffset.x;
            newElement.y += this.clipboardOffset.y;
            
            // 确保元素ID唯一
            if (newElement.id) {
                newElement.id = `element_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            }
            newElement.name = `${newElement.type}_${Date.now()}`;
            
            this.elements.push(newElement);
            newElements.push(newElement);
            pastedCount++;
        }
        
        // 选择粘贴的新元素
        this.selectedElement = null;
        this.selectedElements = newElements;
        this.showPropertyPanel(newElements[0]);
        this.saveState();
        this.render();
        
        // 移动偏移量，避免连续粘贴时重叠
        this.clipboardOffset.x += 10;
        this.clipboardOffset.y += 10;
        
        // 偏移量过大时重置
        if (this.clipboardOffset.x > 50) {
            this.clipboardOffset.x = 10;
            this.clipboardOffset.y = 10;
        }
        
        this.showNotification(`✅ 成功粘贴 ${pastedCount} 个元素`, 'success');
    }

    /**
     * 获取矩形框内的所有元素
     * @param {Object} rect - 矩形区域 {x, y, width, height}
     * @returns {Array} 矩形框内的元素数组
     */
    getElementsInRect(rect) {
        const elements = [];
        for (let element of this.elements) {
            if (this.isElementInRect(element, rect)) {
                elements.push(element);
            }
        }
        return elements;
    }

    /**
     * 检测元素是否在矩形框内
     * @param {Object} element - 元素对象
     * @param {Object} rect - 矩形区域 {x, y, width, height}
     * @returns {boolean} 是否在矩形框内
     */
    isElementInRect(element, rect) {
        const bounds = this.getElementBounds(element);
        return !(
            bounds.x + bounds.width < rect.x || 
            bounds.x > rect.x + rect.width ||
            bounds.y + bounds.height < rect.y || 
            bounds.y > rect.y + rect.height
        );
    }

    /**
     * 绘制矩形选择框
     * @param {Object} rect - 矩形区域 {x, y, width, height}
     */
    drawSelectionBox(rect) {
        this.ctx.strokeStyle = "#007bff";
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);
        this.ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
        
        // 绘制半透明填充
        this.ctx.fillStyle = "rgba(0, 123, 255, 0.1)";
        this.ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
        
        this.ctx.setLineDash([]);
    }

    /**
     * 绘制多选元素的边框
     */
    drawMultipleSelectionBorder() {
        if (this.selectedElements.length === 0) return;

        this.ctx.strokeStyle = "#28a745";
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([3, 3]);

        // 计算所有选中元素的联合边界
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        
        for (let element of this.selectedElements) {
            const bounds = this.getElementBounds(element);
            minX = Math.min(minX, bounds.x);
            minY = Math.min(minY, bounds.y);
            maxX = Math.max(maxX, bounds.x + bounds.width);
            maxY = Math.max(maxY, bounds.y + bounds.height);
        }

        // 绘制联合边框
        this.ctx.strokeRect(minX - 5, minY - 5, (maxX - minX) + 10, (maxY - minY) + 10);
        this.ctx.setLineDash([]);

        // 为每个元素绘制独立的选择框
        for (let element of this.selectedElements) {
            this.ctx.strokeStyle = "#28a745";
            this.ctx.lineWidth = 1;
            this.ctx.setLineDash([2, 2]);
            const bounds = this.getElementBounds(element);
            this.ctx.strokeRect(bounds.x - 2, bounds.y - 2, bounds.width + 4, bounds.height + 4);
        }
        this.ctx.setLineDash([]);
    }

    /**
     * 处理多选拖动
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    handleMultipleSelectionMove(mousePos) {
        if (this.isDraggingMultiple && this.selectedElements.length > 0) {
            const deltaX = mousePos.x - this.startX - this.dragOffset.x;
            const deltaY = mousePos.y - this.startY - this.dragOffset.y;

            for (let element of this.selectedElements) {
                if (element.type === "brush") {
                    // 画笔元素需要移动所有点
                    element.x += deltaX;
                    element.y += deltaY;
                    
                    if (element.points) {
                        element.points = element.points.map(point => ({
                            x: point.x + deltaX,
                            y: point.y + deltaY
                        }));
                    }
                } else if (element.type === "arrow") {
                    // 箭头元素需要移动起始点和结束点
                    element.startX += deltaX;
                    element.startY += deltaY;
                    element.endX += deltaX;
                    element.endY += deltaY;
                } else {
                    // 其他元素只移动位置
                    element.x += deltaX;
                    element.y += deltaY;
                }
            }

            this.startX = mousePos.x - this.dragOffset.x;
            this.startY = mousePos.y - this.dragOffset.y;
            this.render();
            this.updatePropertyPanelValues();
        }
    }

    /**
     * 开始矩形选择
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    startRectangularSelection(mousePos) {
        this.isMultiSelecting = true;
        this.selectionBox = {
            x: mousePos.x,
            y: mousePos.y,
            width: 0,
            height: 0
        };
    }

    /**
     * 更新矩形选择
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    updateRectangularSelection(mousePos) {
        if (this.isMultiSelecting && this.selectionBox) {
            this.selectionBox.width = mousePos.x - this.selectionBox.x;
            this.selectionBox.height = mousePos.y - this.selectionBox.y;
            this.render();
        }
    }

    /**
     * 完成矩形选择
     * @param {Object} mousePos - 鼠标位置 {x, y}
     */
    finishRectangularSelection(mousePos) {
        if (this.isMultiSelecting && this.selectionBox) {
            // 确保矩形框的宽度和高度为正数
            let rect = {...this.selectionBox};
            if (rect.width < 0) {
                rect.x += rect.width;
                rect.width = Math.abs(rect.width);
            }
            if (rect.height < 0) {
                rect.y += rect.height;
                rect.height = Math.abs(rect.height);
            }

            // 获取矩形框内的所有元素
            const elementsInRect = this.getElementsInRect(rect);
            
            if (elementsInRect.length > 0) {
                // 清除单选，设置多选
                this.selectedElement = null;
                this.selectedElements = elementsInRect;
                this.showPropertyPanel(elementsInRect[0]);
            } else {
                // 没有选中任何元素，清除选择
                this.selectedElement = null;
                this.selectedElements = [];
                this.hidePropertyPanel();
            }

            // 清除选择框
            this.isMultiSelecting = false;
            this.selectionBox = null;
            this.render();
        }
    }
}

// 初始化编辑器
let editor = new ModernImageEditor();