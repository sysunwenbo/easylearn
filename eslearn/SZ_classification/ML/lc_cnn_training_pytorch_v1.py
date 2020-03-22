# -*- coding: utf-8 -*-
"""
Created on Mon Jul 15 15:04:21 2019
This script is used to training a convolutional neural network,
then validate and test this model using validation and test data
@author: Li Chao
Email: lichao19870617@gmail.com
"""

import os
import time
import torch
import torch.nn as nn
from torch.optim import lr_scheduler
import torchvision.transforms as transforms
import numpy as np
import matplotlib.pyplot as plt
from sklearn import preprocessing

from sklearn.metrics import classification_report
from sklearn.metrics import accuracy_score
from sklearn.metrics import roc_auc_score
from sklearn.metrics import roc_curve
from sklearn.metrics import confusion_matrix

# CNN's Hyper parameters
n_node = 246  # number of nodes in the FC network
num_epochs = 15  # if the number of epoch = 15, the performances are 0.8148, 0.75, 0.86, 0.8812.
batch_size = 20
learning_rate = 0.0001
gamma = 0.5
in_channel = 1
num_classes = 2
cov1_kernel_size = [1, 246]
cov1_filter_number = 100
cov2_kernel_size = [246, 1]
cov2_filter_number = 200
fc1_node_number = 100
early_stopping = 0  # If the validation loss reached the first minimum, then stop training.

# Parameters
model_savepath = r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\MLmodel'
date = time.strftime("%Y_%m_%d_%H_%M_%S")
model_savename = 'model_' + str(date)
is_savefig = False
fig_savepath = r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\MLmodel'
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')


#%% utils
class Utils():
    """
    Utilits for preprocessing data
    """
    def __init__(self,                 
                 dataset_our_center_550=r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_470_from_550.npy',
                 dataset_206=r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_206.npy',
                 dataset_COBRE=r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_COBRE.npy',
                 dataset_UCAL=r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_UCLA.npy',):

        self.dataset_our_center_550 = dataset_our_center_550
        self.dataset_206 = dataset_206
        self.dataset_COBRE = dataset_COBRE
        self.dataset_UCAL = dataset_UCAL
        print('Utils initialization\n')


    def prep_data(self, train_data_path, val_data_path, n_node):
        """
        Main function
        1. load data
        3. re_sampling
        4. normalization
        5. 2d to 4d
        6. transfer np.array to torch.tensor
        """
        self.n_node = n_node

        # load data
        feature_our_center_550, label_our_center_550 = self.load_data(self.dataset_our_center_550)
        feature_206, label_206 = self.load_data(self.dataset_206)
        feature_COBRE, label_COBRE = self.load_data(self.dataset_COBRE)
        feature_UCAL, label_UCAL = self.load_data(self.dataset_UCAL)

        # Generate training data and test data
        feature_train = np.concatenate(
            [feature_our_center_550, feature_206, feature_UCAL], axis=0)
        label_train = np.concatenate(
            [label_our_center_550, label_206, label_UCAL], axis=0)
        feature_val = feature_COBRE
        label_val = label_COBRE

        # over-sampling data
        feature_train, label_train = self.re_sampling(feature_train, label_train)

        # 1 normalization
        feature_train = self.normalization(feature_train)
        feature_val = self.normalization(feature_val)

        # 2d to 4d
        feature_train = self.trans_2d_to_4d(feature_train)
        feature_val = self.trans_2d_to_4d(feature_val)

        # 3 transfer np.array to torch.tensor
        feature_train, label_train = torch.Tensor(feature_train), torch.Tensor(label_train)
        feature_val, label_val = torch.Tensor(feature_val), torch.Tensor(label_val)

        feature_train = torch.utils.data.DataLoader(feature_train, batch_size=batch_size, shuffle=False)
        label_train = torch.utils.data.DataLoader(label_train, batch_size=batch_size, shuffle=False)
        feature_val = feature_val.cuda()
        label_val = label_val.cuda()

        return feature_train, label_train, feature_val, label_val

    def load_data(self, data_path):
        """
        Load data and label
        """
        data = np.load(data_path)
        feature = data[:,2:]
        label = data[:,1]
        return feature, label

    def re_sampling(self,feature, label):
        """
        Used to over-sampling unbalanced data
        """
        #        from imblearn.over_sampling import RandomOverSampler
        #        rus = RandomOverSampler(random_state=0)
        # from imblearn.over_sampling import SMOTE, ADASYN,  KMeansSMOTE
        # sm = KMeansSMOTE(random_state=0)
        # feature_resampled, label_resampled = sm.fit_resample(feature, label)
        # feature_resampled, label_resampled = ADASYN().fit_resample(feature, label)
        from imblearn.over_sampling import RandomOverSampler
        ros = RandomOverSampler(random_state=0)
        feature_resampled, label_resampled = ros.fit_resample(feature, label)
        from collections import Counter
        print(f'orignal label={sorted(Counter(label).items())}')
        print(f'resample label={sorted(Counter(label_resampled).items())}')

        return feature_resampled, label_resampled

    def normalization(self, data):
        """ 
        Used to normalize (standardization) data (zero mean and one unit std: de-mean and devided by std)
        Because of our normalization level is on subject,
        we should transpose the data matrix on python(but not on matlab)
        """
        scaler = preprocessing.StandardScaler().fit(data.T)
        z_data = scaler.transform(data.T) .T
        return z_data


    def trans_2d_to_4d(self, data_2d):
        """ 
        Transfer the 2d data to 4d data, so that the pytorch can handle the data
        """
        n_node = self.n_node
        mask = np.ones([n_node, n_node])
        mask = np.triu(mask, 1) == 1  # 前期只提取了上三角（因为其他的为重复）
        data_4d = np.zeros([len(data_2d), 1, n_node, n_node])
        for i in range(data_4d.shape[0]):
            # 1) 将1维的上三角矩阵向量，嵌入到矩阵的上三角上
            data_4d[i, 0, mask] = data_2d[i, :]
            # 2) 将上三角矩阵，对称地镜像到下三角，从而组成完整的矩阵
            data_4d[i, 0, :, :] += data_4d[i, 0, :, :].T
            # 3) 对角线补上1
            data_4d[i, 0, :, :] += np.eye(n_node)
        return data_4d

    def eval_prformance(self, y_real, y_pred, y_pred_prob):
        """
        Used to evaluate the model preformances
        """
        accuracy = float('%.4f' % (accuracy_score(y_real, y_pred)))
        report = classification_report(y_real, y_pred)
        report = report.split('\n')
        specificity = report[2].strip().split(' ')
        sensitivity = report[3].strip().split(' ')
        specificity = float([spe for spe in specificity if spe != ''][2])
        sensitivity = float([sen for sen in sensitivity if sen != ''][2])
        auc_score = float('%.4f' % roc_auc_score(y_real, y_pred_prob[:, 1]))
        return accuracy, sensitivity, specificity, auc_score


    def plor_roc(self, real_label, predict_label,is_savefig=0, fig_savepath=os.getcwd, fig_savename = 'ROC.tif'):
        """
        plot ROC and return the best threshold
        """    
        fpr, tpr, thresh = roc_curve(real_label, predict_label)

        # identify best thresh (according yuden idex)
        yuden_idx = (1-fpr)+tpr-1
        loc = np.where(yuden_idx==np.max(yuden_idx))
        best_thresh = thresh[loc]

        plt.figure()
        plt.title('ROC Curve')
        plt.xlabel('False Positive Rate', fontsize=10)
        plt.ylabel('True Positive Rate', fontsize=10)
        plt.grid(True)
        plt.plot(fpr, tpr,'-')
        plt.plot(fpr[loc], tpr[loc],'o')

        # 设置坐标轴在axes正中心
        ax = plt.gca()
        ax.spines['top'].set_visible(False) #去掉上边框
        ax.spines['right'].set_visible(False) #
        ax.xaxis.set_ticks_position('bottom')  # 底部‘脊梁’设置为X轴
        ax.spines['bottom'].set_position(('data', 0))  # 底部'脊梁'移动位置，y的data
        ax.yaxis.set_ticks_position('left')  # 左部‘脊梁’设置为Y轴
        ax.spines['left'].set_position(('data', 0))  # 左部‘脊梁’移动位置，x的data
        # save figure
        if is_savefig:
            plt.savefig(os.path.join(fig_savepath, fig_savename), dpi=1200, bbox_inches='tight')

        return best_thresh


#%% Convolutional neural network (two convolutional layers)
class ConvNet(nn.Module):
    """
    This class is used to build CNN model
    """
    def __init__(self, num_classes=2):
        super(ConvNet, self).__init__()
        self.layer1 = nn.Sequential(
        nn.Conv2d(in_channel, cov1_filter_number,
        kernel_size=cov1_kernel_size, stride=1, padding=0),
        nn.BatchNorm2d(cov1_filter_number),
        nn.ReLU())

        self.layer2 = nn.Sequential(
        nn.Conv2d(cov1_filter_number, cov2_filter_number,
        kernel_size=cov2_kernel_size, stride=1, padding=0),
        nn.BatchNorm2d(cov2_filter_number),
        nn.ReLU())

        self.fc1 = nn.Linear(cov2_filter_number, fc1_node_number)
        self.dropout = nn.Dropout(p=0.4, inplace=False)
        self.fc2 = nn.Linear(fc1_node_number, num_classes)
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        out = self.layer1(x)
        out = self.layer2(out)
        out = out.reshape(out.size(0), -1)
        out = self.fc1(out)
        out = self.dropout(out)
        out = self.fc2(out)
        out = self.softmax(out)
        return out


#%% training, validation and testing
class TrainValidation(Utils):
    """
    This class is used to train validation and testing.
    """
    def __init__(self):
        super().__init__()

    def train_and_validation(self, feature_train, label_train, feature_val, label_val):
        model = ConvNet(num_classes).to(device)

        # Loss_train and optimizer
        optimizer = torch.optim.Adam(model.parameters(),lr=learning_rate)
        criterion = nn.CrossEntropyLoss()
        scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=gamma, last_epoch=-1)  # ajust learning_rate

        # Train the model
        total_step = len(feature_train)
        Loss_train = []
        Loss_validation = []
        # Make sure save the model that trained at least one batch size sample.
        # compare_loss is used to find the 
        compare_loss = np.inf
        # Marker of the minimum validation loss
        loss_val = np.inf
        marker = 0
        count = 0
        for epoch in range(num_epochs):
            # marker==1 means already reached best model
            if marker == 1:
                break

            scheduler.step()
            for i, (images, labels) in enumerate(zip(feature_train, label_train)):
                count += 1
                images = images.to(device)
                labels = labels.to(device)

                # Forward pass
                model.train()
                outputs = model(images)

                # tmp saving the model for saving the best model
                model_beforetrain = model

                # make sure labels is scalar type long
                labels = labels.long()
                loss_train = criterion(outputs, labels)

                # Backward and optimize
                optimizer.zero_grad()
                loss_train.backward()
                optimizer.step()

                # Updata training loss
                Loss_train.append(loss_train.item())

                # Switch to evaluation mode and ***
                # Updata validation loss
                model.eval()
                outputs_val = model(feature_val)
                label_val = label_val.long()
                loss_val = criterion(outputs_val, label_val)
                Loss_validation.append(loss_val.item())

                if (i + 1) % 2 == 0:
                    # train loss_train
                    print('Epoch [{}/{}], Step [{}/{}], Loss_train: {:.4f}, loss_val: {:.4f}'
                    .format(epoch + 1, num_epochs, i + 1, total_step, loss_train.item(), loss_val.item()))

                # Save the model checkpoint
                # if reach the first minimum validation loss
                # then save the model
                if early_stopping:
                    if (loss_val > compare_loss) and (marker != 1):
                        marker = 1
                        torch.save(model_beforetrain, os.path.join(model_savepath, ''.join([model_savename, '.ckpt'])))
                        print(f'***Already found the best model***\nEarly Stoped!\n')
                        break
                    else:
                        compare_loss = loss_val

        # if marker of the minimum validation loss is 0
        # then save the last model          
        if marker == 0 or (not early_stopping):
            model_beforetrain = model
            torch.save(model_beforetrain, os.path.join(model_savepath, ''.join([model_savename, '.ckpt'])))

        return model_beforetrain, Loss_train, Loss_validation


    def validata(self, model, data, label):
        """
        Idengity the best thresh (max yuden idex) using pre-trained model(load from local device)
        """
        data, label, model = data.cpu(), label.cpu(), model.cpu()
        output = model(data)
        _, predicted = torch.max(output.data, 1)
        accuracy, sensitivity, specificity, auc_score = self.eval_prformance(label, predicted, output.data)

        best_thresh = self.plor_roc(label, output.data[:,1], is_savefig=is_savefig,fig_savepath=fig_savepath, fig_savename='ROC_val.tif')

        return accuracy, sensitivity, specificity, auc_score, best_thresh

#%%
if __name__ == '__main__':
    self = Utils()
    train_validation = TrainValidation()

    # prepare data
    feature_train, label_train, feature_val, label_val = self.prep_data(
    train_data_path = r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_COBRE.npy',
    val_data_path = r'D:\WorkStation_2018\WorkStation_CNN_Schizo\Data\ML_data_npy\dataset_206.npy',
    n_node = 246) 

    # training
    model, Loss_train, Loss_validation = train_validation.train_and_validation(
    feature_train, label_train, feature_val, label_val)

    # test model
    model.eval()
    accuracy_val, sensitivity_val, specificity_val, auc_score_val, best_thresh = train_validation.validata(model, feature_val, label_val)
    print(f'validation:acc/sens/spec/auc are\n {accuracy_val}, {sensitivity_val}, {specificity_val}, {auc_score_val}\n')

    #%% show
    # show loss_train
    plt.figure()
    plt.plot(Loss_train)
    plt.plot(Loss_validation)
    plt.show()